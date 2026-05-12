package video

import (
	"encoding/json"
	"fmt"
	"image"
	"image/color"
	"image/draw"
	"image/jpeg"
	"log"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"
	"time"

	"gocv.io/x/gocv"
)

// FrameDetection represents detection results for a single frame
type FrameDetection struct {
	Frame         int              `json:"frame"`
	TimestampSec  float64          `json:"timestamp_sec"`
	HasViolation  bool             `json:"has_violation"`
	Persons       []PersonResult   `json:"persons"`
	Env           []EnvResult      `json:"env"`
	Road          []RoadResult     `json:"road"`
	SafetyCones   []SafetyConeResult `json:"safety_cones"`
}

// PersonResult represents a detected person
type PersonResult struct {
	BBox       []int     `json:"bbox"`
	Confidence float64   `json:"confidence"`
	Violations []string `json:"violations"`
}

// EnvResult represents an environmental hazard
type EnvResult struct {
	ClassName string  `json:"class_name"`
	Confidence float64 `json:"confidence"`
	BBox      []int   `json:"bbox"`
}

// RoadResult represents road damage
type RoadResult struct {
	ClassName  string  `json:"class_name"`
	Confidence float64 `json:"confidence"`
	BBox       []int   `json:"bbox"`
}

// SafetyConeResult represents a safety cone detection
type SafetyConeResult struct {
	ClassName  string  `json:"class_name"`
	Confidence float64 `json:"confidence"`
	BBox       []int   `json:"bbox"`
}

// VideoInfo contains video metadata
type VideoInfo struct {
	TotalFrames      int     `json:"total_frames"`
	FPS              float64 `json:"fps"`
	Width            int     `json:"width"`
	Height           int     `json:"height"`
	ProcessedFrames  int     `json:"processed_frames"`
}

// VideoResult contains the complete video processing result
type VideoResult struct {
	VideoInfo   VideoInfo       `json:"video_info"`
	Frames      []FrameDetection `json:"frames"`
	Summary     VideoSummary    `json:"summary"`
}

// VideoSummary contains aggregated statistics
type VideoSummary struct {
	TotalViolationFrames int `json:"total_violation_frames"`
	TotalPersonsDetected int `json:"total_persons_detected"`
	TotalEnvHazards      int `json:"total_env_hazards"`
	TotalRoadDamage      int `json:"total_road_damage"`
	TotalSafetyCones     int `json:"total_safety_cones"`
}

// Job represents a video processing job
type Job struct {
	ID                 int
	Status             string // pending, processing, done, failed
	Progress           int
	TotalFrames        int
	ProcessedFrames    int
	Filename           string
	FilePath           string
	OutputPath         string
	ErrorMessage       string
	CreatedAt          time.Time
	CompletedAt        *time.Time
	Result             *VideoResult
}

// Processor handles video processing
type Processor struct {
	mu          sync.Mutex
	jobs        map[int]*Job
	nextJobID   int
	inferenceURL string
}

// NewProcessor creates a new video processor
func NewProcessor(inferenceURL string) *Processor {
	if inferenceURL == "" {
		inferenceURL = "http://localhost:8001"
	}
	return &Processor{
		jobs:          make(map[int]*Job),
		nextJobID:     1,
		inferenceURL: inferenceURL,
	}
}

// CreateJob creates a new video processing job
func (p *Processor) CreateJob(filename, filePath string) *Job {
	p.mu.Lock()
	defer p.mu.Unlock()

	job := &Job{
		ID:        p.nextJobID,
		Status:    "pending",
		Filename:  filename,
		FilePath:  filePath,
		CreatedAt: time.Now(),
	}
	p.jobs[p.nextJobID] = job
	p.nextJobID++
	return job
}

// GetJob returns a job by ID
func (p *Processor) GetJob(id int) *Job {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.jobs[id]
}

// GetAllJobs returns all jobs
func (p *Processor) GetAllJobs() []*Job {
	p.mu.Lock()
	defer p.mu.Unlock()

	jobs := make([]*Job, 0, len(p.jobs))
	for _, job := range p.jobs {
		jobs = append(jobs, job)
	}
	return jobs
}

// ProcessVideo processes a video file and returns the result
func (p *Processor) ProcessVideo(jobID int) error {
	job := p.GetJob(jobID)
	if job == nil {
		return fmt.Errorf("job %d not found", jobID)
	}

	job.Status = "processing"
	log.Printf("[VIDEO] Processing job %d: %s", jobID, job.FilePath)

	// Open video file
	cap, err := gocv.VideoCaptureFile(job.FilePath)
	if err != nil {
		job.Status = "failed"
		job.ErrorMessage = fmt.Sprintf("Failed to open video: %v", err)
		return err
	}
	defer cap.Close()

	if !cap.IsOpened() {
		job.Status = "failed"
		job.ErrorMessage = "Failed to open video file"
		return fmt.Errorf("failed to open video")
	}

	// Get video properties
	job.TotalFrames = int(cap.Get(gocv.VideoCaptureFrameCount))
	fps := cap.Get(gocv.VideoCaptureFPS)
	if fps == 0 {
		fps = 25.0
	}
	width := int(cap.Get(gocv.VideoCaptureFrameWidth))
	height := int(cap.Get(gocv.VideoCaptureFrameHeight))

	log.Printf("[VIDEO] Video info: %dx%d, %f fps, %d frames",
		width, height, fps, job.TotalFrames)

	// Create output directory
	outputDir := filepath.Join(filepath.Dir(job.FilePath), "annotated")
	os.MkdirAll(outputDir, 0755)
	job.OutputPath = filepath.Join(outputDir, job.Filename)

	// Process frames
	result := p.processFrames(cap, job, width, height, fps)
	job.Result = result
	job.Status = "done"
	job.Progress = 100
	job.ProcessedFrames = result.VideoInfo.ProcessedFrames

	now := time.Now()
	job.CompletedAt = &now

	log.Printf("[VIDEO] Job %d completed: %d/%d frames processed",
		jobID, result.VideoInfo.ProcessedFrames, job.TotalFrames)

	return nil
}

// processFrames processes all frames of a video
func (p *Processor) processFrames(cap *gocv.VideoCapture, job *Job, width, height int, fps float64) *VideoResult {
	frameInterval := 5 // Process every 5th frame
	maxFrames := 2000  // Max frames to process

	result := &VideoResult{
		VideoInfo: VideoInfo{
			TotalFrames: job.TotalFrames,
			FPS:         fps,
			Width:       width,
			Height:      height,
		},
		Frames:   make([]FrameDetection, 0),
		Summary:  VideoSummary{},
	}

	frameIdx := 0
	processed := 0
	frame := gocv.NewMat()
	defer frame.Close()

	for processed < maxFrames {
		if !cap.Read(&frame) {
			break
		}

		frameIdx++

		// Skip frames not at interval
		if frameIdx%frameInterval != 0 {
			continue
		}

		// Convert frame to JPEG for inference
		imgBytes, err := gocv.IMEncode(".jpg", frame)
		if err != nil {
			log.Printf("[VIDEO] Failed to encode frame %d: %v", frameIdx, err)
			continue
		}

		// Call inference service
		detections := p.callInference(imgBytes.GetBytes())
		imgBytes.Close()

		// Draw detections on frame
		annotated := p.drawDetections(frame, detections)

		// Save annotated frame as JPEG
		outputFile := filepath.Join(filepath.Dir(job.OutputPath),
			fmt.Sprintf("frame_%06d.jpg", frameIdx))
		gocv.IMWrite(outputFile, annotated)

		// Calculate timestamp
		timestampSec := float64(frameIdx) / fps

		// Check for violations
		hasViolation := len(detections.Persons) > 0 && len(detections.Persons[0].Violations) > 0
		hasViolation = hasViolation || len(detections.Env) > 0 || len(detections.Road) > 0

		frameDet := FrameDetection{
			Frame:         frameIdx,
			TimestampSec:  timestampSec,
			HasViolation:  hasViolation,
			Persons:       detections.Persons,
			Env:           detections.Env,
			Road:          detections.Road,
			SafetyCones:   detections.SafetyCones,
		}
		result.Frames = append(result.Frames, frameDet)

		// Update summary
		if hasViolation {
			result.Summary.TotalViolationFrames++
		}
		result.Summary.TotalPersonsDetected += len(detections.Persons)
		result.Summary.TotalEnvHazards += len(detections.Env)
		result.Summary.TotalRoadDamage += len(detections.Road)
		result.Summary.TotalSafetyCones += len(detections.SafetyCones)

		processed++

		// Update job progress
		if processed%50 == 0 {
			job.ProcessedFrames = processed
			job.Progress = int(float64(frameIdx) / float64(job.TotalFrames) * 100)
			log.Printf("[VIDEO] Job %d progress: %d/%d frames (%.1f%%)",
				job.ID, processed, job.TotalFrames, float64(job.Progress))
		}

		annotated.Close()
	}

	result.VideoInfo.ProcessedFrames = processed
	return result
}

// InferenceResponse represents the response from inference service
type InferenceResponse struct {
	Persons []PersonResult `json:"persons"`
	Env     []EnvResult    `json:"env"`
	Road    []RoadResult   `json:"road"`
}

// callInference calls the Python inference service
func (p *Processor) callInference(frameBytes []byte) *InferenceResponse {
	// For now, return empty response - actual implementation calls Python service
	// This will be implemented when we integrate with the inference service
	return &InferenceResponse{
		Persons: []PersonResult{},
		Env:     []EnvResult{},
		Road:    []RoadResult{},
	}
}

// drawDetections draws bounding boxes on the frame
func (p *Processor) drawDetections(frame gocv.Mat, detections *InferenceResponse) gocv.Mat {
	// Create a copy to draw on
	result := frame.Clone()

	// Define colors
	red := color.RGBA{255, 0, 0, 255}
	green := color.RGBA{0, 255, 0, 255}
	blue := color.RGBA{0, 0, 255, 255}
	orange := color.RGBA{255, 165, 0, 255}

	// Draw persons
	for _, person := range detections.Persons {
		if len(person.BBox) != 4 {
			continue
		}
		x1, y1, x2, y2 := person.BBox[0], person.BBox[1], person.BBox[2], person.BBox[3]

		color := green
		if len(person.Violations) > 0 {
			color = red
		}

		gocv.Rectangle(&result, image.Rect(x1, y1, x2, y2), color, 2)

		label := fmt.Sprintf("Person %.0f%%", person.Confidence*100)
		if len(person.Violations) > 0 {
			label = fmt.Sprintf("BAHAYA %.0f%%", person.Confidence*100)
		}
		gocv.PutText(&result, label, image.Point{x1, y1-10},
			gocv.FontHersheySimplex, 0.5, color, 2)
	}

	// Draw environmental hazards
	for _, env := range detections.Env {
		if len(env.BBox) != 4 {
			continue
		}
		x1, y1, x2, y2 := env.BBox[0], env.BBox[1], env.BBox[2], env.BBox[3]

		gocv.Rectangle(&result, image.Rect(x1, y1, x2, y2), red, 2)
		label := fmt.Sprintf("DANGER: %s %.0f%%", env.ClassName, env.Confidence*100)
		gocv.PutText(&result, label, image.Point{x1, y1-10},
			gocv.FontHersheySimplex, 0.5, red, 2)
	}

	// Draw road damage
	for _, road := range detections.Road {
		if len(road.BBox) != 4 {
			continue
		}
		x1, y1, x2, y2 := road.BBox[0], road.BBox[1], road.BBox[2], road.BBox[3]

		gocv.Rectangle(&result, image.Rect(x1, y1, x2, y2), orange, 2)
		label := fmt.Sprintf("ROAD: %s %.0f%%", road.ClassName, road.Confidence*100)
		gocv.PutText(&result, label, image.Point{x1, y1-10},
			gocv.FontHersheySimplex, 0.5, orange, 2)
	}

	return result
}

// CreateAnnotatedVideo creates a video from annotated frames
func (p *Processor) CreateAnnotatedVideo(job *Job) error {
	outputDir := filepath.Dir(job.OutputPath)
	outputFile := filepath.Join(outputDir, job.Filename+"_annotated.mp4")

	// Get first frame to determine size
	firstFrameFile := filepath.Join(outputDir, "frame_000001.jpg")
	if _, err := os.Stat(firstFrameFile); os.IsNotExist(err) {
		return fmt.Errorf("no frames found to create video")
	}

	img := gocv.IMRead(firstFrameFile, gocv.IMReadColor)
	if img.Empty() {
		return fmt.Errorf("failed to read first frame")
	}
	width := img.Cols()
	height := img.Rows()
	img.Close()

	// Use FFmpeg to create video from frames
	cmd := exec.Command("ffmpeg",
		"-y",                           // Overwrite output
		"-framerate", "25",             // FPS
		"-i", filepath.Join(outputDir, "frame_%06d.jpg"),
		"-c:v", "libx264",             // H264 codec
		"-pix_fmt", "yuv420p",
		"-crf", "23",                  // Quality
		outputFile,
	)

	if runtime.GOOS == "windows" {
		cmd = exec.Command("cmd", "/c",
			"ffmpeg -y -framerate 25 -i \""+filepath.Join(outputDir, "frame_%06d.jpg")+
				"\" -c:v libx264 -pix_fmt yuv420p -crf 23 \""+outputFile+"\"")
	}

	output, err := cmd.CombinedOutput()
	if err != nil {
		log.Printf("[VIDEO] FFmpeg error: %v, output: %s", err, string(output))
		// Try without specifying codec
		cmd = exec.Command("ffmpeg",
			"-y",
			"-framerate", "25",
			"-i", filepath.Join(outputDir, "frame_%06d.jpg"),
			outputFile,
		)
		output, err = cmd.CombinedOutput()
		if err != nil {
			log.Printf("[VIDEO] FFmpeg fallback error: %v, output: %s", err, string(output))
			return fmt.Errorf("failed to create video: %v", err)
		}
	}

	job.OutputPath = outputFile
	log.Printf("[VIDEO] Created annotated video: %s", outputFile)
	return nil
}

// GetResultJSON returns the job result as JSON
func (p *Processor) GetResultJSON(jobID int) (string, error) {
	job := p.GetJob(jobID)
	if job == nil {
		return "", fmt.Errorf("job not found")
	}

	if job.Result == nil {
		return "", fmt.Errorf("no result available")
	}

	data, err := json.Marshal(job.Result)
	if err != nil {
		return "", err
	}
	return string(data), nil
}
