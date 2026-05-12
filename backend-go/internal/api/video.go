package api

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/aryarefman/migas-siews/backend-go/internal/video"
)

// VideoJob represents a video processing job
type VideoJob struct {
	ID                  int        `json:"id"`
	Filename            string     `json:"filename"`
	Status              string     `json:"status"`
	Progress            int        `json:"progress"`
	TotalFrames         int        `json:"total_frames"`
	ProcessedFrames     int        `json:"processed_frames"`
	AnnotatedVideoPath  string     `json:"annotated_video_path,omitempty"`
	ErrorMessage        string     `json:"error_message,omitempty"`
	CreatedAt           time.Time  `json:"created_at"`
	CompletedAt         *time.Time `json:"completed_at,omitempty"`
}

var (
	videoJobs      = make(map[int]*video.Job)
	videoJobsMutex sync.Mutex
	nextVideoJobID = 1
	videoProcessor *video.Processor
)

func init() {
	// Initialize video processor
	inferenceURL := os.Getenv("INFERENCE_URL")
	if inferenceURL == "" {
		inferenceURL = "http://localhost:8001"
	}
	videoProcessor = video.NewProcessor(inferenceURL)
}

// UploadVideo handles video file upload
func (s *Server) UploadVideo(c *gin.Context) {
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No file uploaded"})
		return
	}
	defer file.Close()

	// Validate file type
	ext := strings.ToLower(filepath.Ext(header.Filename))
	allowedExts := map[string]bool{".mp4": true, ".avi": true, ".mkv": true, ".mov": true, ".webm": true}
	if !allowedExts[ext] {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Unsupported file type"})
		return
	}

	// Create uploads directory
	uploadsDir := filepath.Join(s.staticDir, "uploads")
	os.MkdirAll(uploadsDir, 0755)

	// Save file
	ts := time.Now().UTC().Format("20060102_150405")
	filename := fmt.Sprintf("%s_%s", ts, strings.ReplaceAll(header.Filename, " ", "_"))
	filePath := filepath.Join(uploadsDir, filename)

	out, err := os.Create(filePath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to save file"})
		return
	}
	defer out.Close()

	if _, err := io.Copy(out, file); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to save file"})
		return
	}

	// Create job
	videoJobsMutex.Lock()
	job := videoProcessor.CreateJob(header.Filename, filePath)
	jobID := job.ID
	nextVideoJobID++
	videoJobsMutex.Unlock()

	log.Printf("[VIDEO] Uploaded: %s (job %d)", filename, jobID)

	// Start processing in background
	go func() {
		if err := videoProcessor.ProcessVideo(jobID); err != nil {
			log.Printf("[VIDEO] Job %d failed: %v", jobID, err)
		} else {
			// Create annotated video from frames
			j := videoProcessor.GetJob(jobID)
			if j != nil {
				if err := videoProcessor.CreateAnnotatedVideo(j); err != nil {
					log.Printf("[VIDEO] Failed to create annotated video: %v", err)
				}
			}
		}
	}()

	c.JSON(http.StatusOK, gin.H{
		"job_id":  jobID,
		"filename": header.Filename,
		"status":   "pending",
		"message":  "Video uploaded. Processing started.",
	})
}

// GetVideoJobs returns all video jobs
func (s *Server) GetVideoJobs(c *gin.Context) {
	videoJobsMutex.Lock()
	jobs := make([]VideoJob, 0, len(videoJobs))
	for _, j := range videoJobs {
		jobs = append(jobs, VideoJob{
			ID:                  j.ID,
			Filename:            j.Filename,
			Status:              j.Status,
			Progress:            j.Progress,
			TotalFrames:         j.TotalFrames,
			ProcessedFrames:     j.ProcessedFrames,
			AnnotatedVideoPath:  j.OutputPath,
			ErrorMessage:        j.ErrorMessage,
			CreatedAt:           j.CreatedAt,
			CompletedAt:         j.CompletedAt,
		})
	}
	videoJobsMutex.Unlock()

	c.JSON(http.StatusOK, jobs)
}

// GetVideoJob returns a specific video job
func (s *Server) GetVideoJob(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid job ID"})
		return
	}

	videoJobsMutex.Lock()
	job, exists := videoJobs[id]
	videoJobsMutex.Unlock()

	if !exists {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	c.JSON(http.StatusOK, VideoJob{
		ID:                  job.ID,
		Filename:            job.Filename,
		Status:              job.Status,
		Progress:            job.Progress,
		TotalFrames:         job.TotalFrames,
		ProcessedFrames:     job.ProcessedFrames,
		AnnotatedVideoPath:  job.OutputPath,
		ErrorMessage:        job.ErrorMessage,
		CreatedAt:           job.CreatedAt,
		CompletedAt:         job.CompletedAt,
	})
}

// GetVideoResult returns the detection results for a completed job
func (s *Server) GetVideoResult(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid job ID"})
		return
	}

	job := videoProcessor.GetJob(id)
	if job == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	if job.Status != "done" {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("Job not done. Status: %s", job.Status)})
		return
	}

	result, err := videoProcessor.GetResultJSON(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	var resultData map[string]interface{}
	json.Unmarshal([]byte(result), &resultData)

	c.JSON(http.StatusOK, gin.H{
		"job_id":                  job.ID,
		"filename":                job.Filename,
		"status":                  job.Status,
		"total_frames_processed":  job.ProcessedFrames,
		"annotated_video_path":    job.OutputPath,
		"result":                  resultData,
	})
}

// DeleteVideoJob deletes a video job and its files
func (s *Server) DeleteVideoJob(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid job ID"})
		return
	}

	job := videoProcessor.GetJob(id)
	if job == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	// Delete files
	if job.FilePath != "" {
		os.Remove(job.FilePath)
	}
	if job.OutputPath != "" {
		os.Remove(job.OutputPath)
	}

	// Remove from jobs map
	videoJobsMutex.Lock()
	delete(videoJobs, id)
	videoJobsMutex.Unlock()

	c.JSON(http.StatusOK, gin.H{"status": "deleted", "id": id})
}

// RegisterVideoRoutes registers video-related routes
func (s *Server) RegisterVideoRoutes() {
	// Note: Routes are registered in setupRoutes() in server.go
}
