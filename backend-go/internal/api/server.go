pretpackage api

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/aryarefman/migas-siews/backend-go/internal/detector"
	"github.com/aryarefman/migas-siews/backend-go/internal/models"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"gorm.io/gorm"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins for development
	},
}

// Server wraps the HTTP server
type Server struct {
	engine    *gin.Engine
	pipeline  *detector.Pipeline
	db        *gorm.DB
	whatsapp  *FonnteClient
	staticDir string
}

// NewServer creates a new API server
func NewServer(pipeline *detector.Pipeline, db *gorm.DB) *Server {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()
	engine.Use(gin.Logger(), gin.Recovery())

	// Set up static file serving
	staticDir := os.Getenv("STATIC_DIR")
	if staticDir == "" {
		staticDir = "./static"
	}
	os.MkdirAll(staticDir, os.ModePerm)
	engine.Static("/static", staticDir)

	return &Server{
		engine:    engine,
		pipeline:  pipeline,
		db:        db,
		whatsapp:  NewFonnteClient(),
		staticDir: staticDir,
	}
}

// Run starts the HTTP server
func (s *Server) Run(addr string) error {
	s.setupRoutes()
	return s.engine.Run(addr)
}

func (s *Server) setupRoutes() {
	// CORS middleware
	s.engine.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	// Health check
	s.engine.GET("/health", s.healthCheck)

	// Note: Static files are served in NewServer

	// API routes - use same handler functions
	// These routes are registered at both / and /api for compatibility
	api := s.engine.Group("/api")
	{
		// Image analysis
		api.POST("/analyze/image", s.analyzeImage)
		api.POST("/analyze/upload", s.uploadAndAnalyze)

		// Polygons/Zones
		api.GET("/polygons", s.listPolygons)
		api.POST("/polygons", s.createPolygon)
		api.PUT("/polygons/:id", s.updatePolygon)
		api.DELETE("/polygons/:id", s.deletePolygon)

		// Alerts
		api.GET("/alerts", s.listAlerts)
		api.POST("/alerts/:id/resolve", s.resolveAlert)
		api.POST("/alerts/:id/false-positive", s.markFalsePositive)
		api.GET("/alerts/:id/detections", s.getAlertDetections)

		// Shutdown
		api.POST("/shutdown/trigger", s.triggerShutdown)

		// Settings
		api.GET("/settings", s.getSettings)
		api.POST("/settings", s.updateSettings)
		api.POST("/settings/notify-test", s.testNotification)

		// Stats
		api.GET("/stats", s.getStats)
		api.GET("/analytics/compliance", s.getComplianceAnalytics)

		// Video jobs
		api.POST("/video/upload", s.uploadVideo)
		api.GET("/video/jobs", s.listVideoJobs)
		api.GET("/video/jobs/:id", s.getVideoJob)
		api.GET("/video/jobs/:id/result", s.getVideoResult)
		api.DELETE("/video/jobs/:id", s.deleteVideoJob)
	}

	// Also register routes at root level (without /api prefix) for frontend compatibility
	// Image analysis
	s.engine.POST("/analyze/image", s.analyzeImage)
	s.engine.POST("/analyze/upload", s.uploadAndAnalyze)

	// Polygons/Zones
	s.engine.GET("/polygons", s.listPolygons)
	s.engine.POST("/polygons", s.createPolygon)
	s.engine.PUT("/polygons/:id", s.updatePolygon)
	s.engine.DELETE("/polygons/:id", s.deletePolygon)

	// Alerts
	s.engine.GET("/alerts", s.listAlerts)
	s.engine.POST("/alerts/:id/resolve", s.resolveAlert)
	s.engine.POST("/alerts/:id/false-positive", s.markFalsePositive)
	s.engine.GET("/alerts/:id/detections", s.getAlertDetections)

	// Shutdown
	s.engine.POST("/shutdown/trigger", s.triggerShutdown)

	// Settings
	s.engine.GET("/settings", s.getSettings)
	s.engine.POST("/settings", s.updateSettings)
	s.engine.POST("/settings/notify-test", s.testNotification)

	// Stats
	s.engine.GET("/stats", s.getStats)
	s.engine.GET("/analytics/compliance", s.getComplianceAnalytics)

	// Video jobs
	s.engine.POST("/video/upload", s.uploadVideo)
	s.engine.GET("/video/jobs", s.listVideoJobs)
	s.engine.GET("/video/jobs/:id", s.getVideoJob)
	s.engine.GET("/video/jobs/:id/result", s.getVideoResult)
	s.engine.DELETE("/video/jobs/:id", s.deleteVideoJob)

	// Stream endpoint (for streaming video)
	s.engine.GET("/stream", s.streamHandler)

	// WebSocket
	s.engine.GET("/ws/stream", s.streamWebSocket)
	s.engine.GET("/ws/alerts", s.alertsWebSocket)
}

// ============================================================================
// Health Check
// ============================================================================

// streamHandler proxies MJPEG stream from Python inference service
func (s *Server) streamHandler(c *gin.Context) {
	// Proxy the MJPEG stream from Python inference service
	inferenceURL := os.Getenv("INFERENCE_URL")
	if inferenceURL == "" {
		inferenceURL = "http://localhost:8001"
	}

	streamURL := inferenceURL + "/stream"

	// Start webcam if not running
	http.Get(inferenceURL + "/webcam/start")

	// Set headers for MJPEG streaming
	c.Header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")

	// Fetch and proxy the stream
	resp, err := http.Get(streamURL)
	if err != nil {
		c.String(http.StatusServiceUnavailable, "Failed to connect to inference service")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		c.String(http.StatusServiceUnavailable, "Inference service stream unavailable")
		return
	}

	// Set content type from upstream
	if ct := resp.Header.Get("Content-Type"); ct != "" {
		c.Header("Content-Type", ct)
	}

	// Proxy the stream
	c.Status(http.StatusOK)
	c.Writer.Flush()

	buf := make([]byte, 65536) // 64KB buffer
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := c.Writer.Write(buf[:n]); werr != nil {
				return
			}
			c.Writer.Flush()
		}
		if err != nil {
			return
		}
	}
}

func (s *Server) healthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":    "ok",
		"service":   "siews-go-backend",
		"version":   "5.0.0",
		"camera":    s.pipeline.IsRunning(),
		"inference": s.pipeline != nil,
	})
}

// ============================================================================
// Image Analysis
// ============================================================================

func (s *Server) analyzeImage(c *gin.Context) {
	var req struct {
		Image string `json:"image"` // Base64 encoded image
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Decode base64 image
	imageData, err := decodeBase64Image(req.Image)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid base64 image"})
		return
	}

	// Call inference service
	if s.pipeline == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Pipeline not available"})
		return
	}

	response, err := s.pipeline.AnalyzeImage(imageData)
	if err != nil {
		log.Printf("Analysis error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

func (s *Server) uploadAndAnalyze(c *gin.Context) {
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No file uploaded"})
		return
	}
	defer file.Close()

	// Validate file type
	ext := filepath.Ext(header.Filename)
	allowedExts := map[string]bool{".jpg": true, ".jpeg": true, ".png": true, ".bmp": true, ".webp": true}
	if !allowedExts[ext] {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Unsupported file type"})
		return
	}

	// Read file data
	imageData, err := io.ReadAll(file)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to read file"})
		return
	}

	// Call inference service
	if s.pipeline == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Pipeline not available"})
		return
	}

	response, err := s.pipeline.AnalyzeImage(imageData)
	if err != nil {
		log.Printf("Analysis error: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

// ============================================================================
// Polygon Zone Management
// ============================================================================

func (s *Server) listPolygons(c *gin.Context) {
	var zones []models.Zone
	s.db.Where("active = ?", true).Order("created_at DESC").Find(&zones)

	result := make([]gin.H, len(zones))
	for i, z := range zones {
		var vertices [][]float64
		json.Unmarshal([]byte(z.VerticesJSON), &vertices)
		result[i] = gin.H{
			"id":         z.ID,
			"name":       z.Name,
			"vertices":   vertices,
			"color":      z.Color,
			"active":     z.Active,
			"risk_level": z.RiskLevel,
		}
	}
	c.JSON(http.StatusOK, result)
}

func (s *Server) createPolygon(c *gin.Context) {
	var req struct {
		Name      string      `json:"name" binding:"required"`
		Vertices  [][]float64 `json:"vertices" binding:"required"`
		Color     string      `json:"color"`
		RiskLevel string      `json:"risk_level"`
		Active    bool        `json:"active"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	verticesJSON, _ := json.Marshal(req.Vertices)
	color := req.Color
	if color == "" {
		color = "#FF0000"
	}
	riskLevel := req.RiskLevel
	if riskLevel == "" {
		riskLevel = "high"
	}

	zone := models.Zone{
		Name:           req.Name,
		VerticesJSON:   string(verticesJSON),
		Color:          color,
		Active:         req.Active,
		RiskLevel:      riskLevel,
		ZoneType:       "restricted",
		DwellThreshold: 10,
	}

	if err := s.db.Create(&zone).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"id":         zone.ID,
		"name":       zone.Name,
		"vertices":   req.Vertices,
		"color":      zone.Color,
		"active":     zone.Active,
		"risk_level": zone.RiskLevel,
	})
}

func (s *Server) updatePolygon(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var zone models.Zone
	if err := s.db.First(&zone, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Zone not found"})
		return
	}

	var req struct {
		Name      *string      `json:"name"`
		Vertices  *[][]float64 `json:"vertices"`
		Color     *string      `json:"color"`
		RiskLevel *string      `json:"risk_level"`
		Active    *bool        `json:"active"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.Name != nil {
		zone.Name = *req.Name
	}
	if req.Vertices != nil {
		verticesJSON, _ := json.Marshal(req.Vertices)
		zone.VerticesJSON = string(verticesJSON)
	}
	if req.Color != nil {
		zone.Color = *req.Color
	}
	if req.RiskLevel != nil {
		zone.RiskLevel = *req.RiskLevel
	}
	if req.Active != nil {
		zone.Active = *req.Active
	}

	s.db.Save(&zone)

	var vertices [][]float64
	json.Unmarshal([]byte(zone.VerticesJSON), &vertices)

	c.JSON(http.StatusOK, gin.H{
		"id":         zone.ID,
		"name":       zone.Name,
		"vertices":   vertices,
		"color":      zone.Color,
		"active":     zone.Active,
		"risk_level": zone.RiskLevel,
	})
}

func (s *Server) deletePolygon(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	result := s.db.Delete(&models.Zone{}, id)
	if result.RowsAffected == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "Zone not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "deleted", "id": id})
}

// ============================================================================
// Alerts
// ============================================================================

func (s *Server) listAlerts(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	zoneID, _ := strconv.Atoi(c.Query("zone_id"))
	riskLevel := c.Query("risk_level")
	resolved := c.Query("resolved")

	if page < 1 {
		page = 1
	}
	if limit < 1 || limit > 100 {
		limit = 20
	}

	query := s.db.Model(&models.Alert{}).Preload("Zone")

	if zoneID > 0 {
		query = query.Where("zone_id = ?", zoneID)
	}
	if riskLevel != "" {
		query = query.Joins("JOIN zones ON alerts.zone_id = zones.id").Where("zones.risk_level = ?", riskLevel)
	}
	if resolved == "true" {
		query = query.Where("resolved = ?", true)
	} else if resolved == "false" {
		query = query.Where("resolved = ?", false)
	}

	var total int64
	query.Count(&total)

	var alerts []models.Alert
	offset := (page - 1) * limit
	query.Order("timestamp DESC").Offset(offset).Limit(limit).Find(&alerts)

	result := make([]gin.H, len(alerts))
	for i, a := range alerts {
		result[i] = gin.H{
			"id":                 a.ID,
			"zone_id":            a.ZoneID,
			"zone_name":          a.Zone.Name,
			"risk_level":         a.Zone.RiskLevel,
			"confidence":         a.Confidence,
			"snapshot_path":      a.SnapshotPath,
			"timestamp":          a.Timestamp,
			"shutdown_triggered": a.ShutdownTriggered,
			"resolved":           a.Resolved,
			"violation_type":     a.ViolationType,
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"total":  total,
		"page":   page,
		"limit":  limit,
		"alerts": result,
	})
}

func (s *Server) resolveAlert(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	result := s.db.Model(&models.Alert{}).Where("id = ?", id).Update("resolved", true)
	if result.RowsAffected == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "Alert not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "resolved", "id": id})
}

func (s *Server) markFalsePositive(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var req struct {
		Reason string `json:"reason"`
	}
	c.ShouldBindJSON(&req)

	s.db.Model(&models.Alert{}).Where("id = ?", id).Updates(map[string]interface{}{
		"false_positive": true,
		"resolved":       true,
	})
	s.db.Model(&models.DetectionLog{}).Where("alert_id = ?", id).Update("is_false_positive", true)

	c.JSON(http.StatusOK, gin.H{"status": "marked_false_positive", "id": id})
}

func (s *Server) getAlertDetections(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var logs []models.DetectionLog
	s.db.Where("alert_id = ?", id).Find(&logs)

	result := make([]gin.H, len(logs))
	for i, l := range logs {
		var bbox []int
		json.Unmarshal([]byte(l.BBoxJSON), &bbox)
		result[i] = gin.H{
			"id":                l.ID,
			"class_name":        l.ClassName,
			"confidence":        l.Confidence,
			"crop_url":          l.CropPath,
			"frame_number":      l.FrameNumber,
			"bbox":              bbox,
			"is_false_positive": l.IsFalsePositive,
		}
	}

	c.JSON(http.StatusOK, result)
}

// ============================================================================
// Shutdown
// ============================================================================

func (s *Server) triggerShutdown(c *gin.Context) {
	var req struct {
		ZoneID int `json:"zone_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var zone models.Zone
	if err := s.db.First(&zone, req.ZoneID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Zone not found"})
		return
	}

	// Trigger relay
	TriggerRelay(zone.Name)

	// Log shutdown
	shutdownLog := models.ShutdownLog{
		ZoneID:        uint(req.ZoneID),
		TriggerSource: "manual",
		TriggeredAt:   time.Now(),
	}
	s.db.Create(&shutdownLog)

	c.JSON(http.StatusOK, gin.H{
		"status":       "triggered",
		"zone_name":    zone.Name,
		"log_id":       shutdownLog.ID,
		"triggered_at": shutdownLog.TriggeredAt,
	})
}
// Settings

func (s *Server) getSettings(c *gin.Context) {
	settings := models.GetAllSettings(s.db)

	// Add stage status
	stages := s.pipeline.GetStagesStatus()
	settings["stages"] = fmt.Sprintf("%v", stages)

	c.JSON(http.StatusOK, settings)
}

func (s *Server) updateSettings(c *gin.Context) {
	var req struct {
		Key   string `json:"key" binding:"required"`
		Value string `json:"value" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.UpdateSetting(s.db, req.Key, req.Value); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Reload pipeline settings if applicable
	if req.Key == "confidence_threshold" || req.Key == "ppe_confidence" {
		s.pipeline.LoadSettings()
	}

	c.JSON(http.StatusOK, gin.H{"status": "updated", "key": req.Key, "value": req.Value})
}

func (s *Server) testNotification(c *gin.Context) {
	settings := models.GetAllSettings(s.db)
	recipients := settings["recipients"]
	facility := settings["facility_name"]

	if recipients == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No recipients configured"})
		return
	}

	err := s.whatsapp.SendTestMessage(recipients, facility)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "sent"})
}

// Stats & Analytics


func (s *Server) getStats(c *gin.Context) {
	todayStart := time.Now().UTC().Truncate(24 * time.Hour)

	var totalZones, activeZones int64
	s.db.Model(&models.Zone{}).Count(&totalZones)
	s.db.Model(&models.Zone{}).Where("active = ?", true).Count(&activeZones)

	var totalAlerts, todayAlerts, unresolved int64
	s.db.Model(&models.Alert{}).Count(&totalAlerts)
	s.db.Model(&models.Alert{}).Where("timestamp >= ?", todayStart).Count(&todayAlerts)
	s.db.Model(&models.Alert{}).Where("resolved = ?", false).Count(&unresolved)

	var totalShutdowns int64
	s.db.Model(&models.ShutdownLog{}).Count(&totalShutdowns)

	var fpToday int64
	s.db.Model(&models.Alert{}).Where("timestamp >= ? AND false_positive = ?", todayStart, true).Count(&fpToday)

	c.JSON(http.StatusOK, gin.H{
		"total_zones":           totalZones,
		"active_zones":          activeZones,
		"total_alerts":          totalAlerts,
		"today_alerts":          todayAlerts,
		"unresolved_alerts":     unresolved,
		"total_shutdowns":       totalShutdowns,
		"false_positives_today": fpToday,
		"camera_status":         "online", // TODO: implement camera status check
	})
}

func (s *Server) getComplianceAnalytics(c *gin.Context) {
	todayStart := time.Now().UTC().Truncate(24 * time.Hour)

	var total, ppeViols, fireSmoke, falsePositives int64
	s.db.Model(&models.Alert{}).Where("timestamp >= ? AND false_positive = ?", todayStart, false).Count(&total)
	s.db.Model(&models.Alert{}).Where("timestamp >= ? AND false_positive = ? AND violation_type IN ?", todayStart, false, []string{"missing_ppe", "no_harness", "multiple"}).Count(&ppeViols)
	s.db.Model(&models.Alert{}).Where("timestamp >= ? AND false_positive = ? AND violation_type = ?", todayStart, false, "fire_smoke").Count(&fireSmoke)
	s.db.Model(&models.Alert{}).Where("timestamp >= ? AND false_positive = ?", todayStart, true).Count(&falsePositives)

	rate := 0.0
	if total+falsePositives > 0 {
		rate = float64(falsePositives) / float64(total+falsePositives) * 100
	}

	c.JSON(http.StatusOK, gin.H{
		"today_total_violations": total,
		"ppe_violations":         ppeViols,
		"fire_smoke_alerts":      fireSmoke,
		"false_positives_today":  falsePositives,
		"false_positive_rate":    rate,
	})
}

// ============================================================================
// Video Jobs
// ============================================================================

func (s *Server) uploadVideo(c *gin.Context) {
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No file uploaded"})
		return
	}
	defer file.Close()

	// Validate file type
	ext := filepath.Ext(header.Filename)
	allowedExts := map[string]bool{".mp4": true, ".avi": true, ".mkv": true, ".mov": true, ".webm": true}
	if !allowedExts[ext] {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Unsupported file type"})
		return
	}

	// Save file
	uploadsDir := filepath.Join(s.staticDir, "uploads")
	os.MkdirAll(uploadsDir, os.ModePerm)

	ts := time.Now().UTC().Format("20060102_150405")
	safeName := fmt.Sprintf("%s_%s", ts, header.Filename)
	destPath := filepath.Join(uploadsDir, safeName)

	out, err := os.Create(destPath)
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
	job := models.VideoJob{
		Filename: header.Filename,
		FilePath: destPath,
		Status:   "pending",
	}
	s.db.Create(&job)

	// Start background processing
	go s.processVideoJob(job.ID)

	c.JSON(http.StatusOK, gin.H{
		"job_id":   job.ID,
		"filename": job.Filename,
		"status":   job.Status,
		"message":  "Video uploaded. Processing started in background.",
	})
}

func (s *Server) processVideoJob(jobID uint) {
	// TODO: Implement video processing
	// This would run the detection pipeline on each frame
}

func (s *Server) listVideoJobs(c *gin.Context) {
	var jobs []models.VideoJob
	s.db.Order("created_at DESC").Limit(50).Find(&jobs)

	result := make([]gin.H, len(jobs))
	for i, j := range jobs {
		result[i] = gin.H{
			"id":               j.ID,
			"filename":         j.Filename,
			"status":           j.Status,
			"progress":         j.Progress,
			"total_frames":     j.TotalFrames,
			"processed_frames": j.ProcessedFrames,
			"created_at":       j.CreatedAt,
			"completed_at":     j.CompletedAt,
		}
	}

	c.JSON(http.StatusOK, result)
}

func (s *Server) getVideoJob(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var job models.VideoJob
	if err := s.db.First(&job, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"id":               job.ID,
		"filename":         job.Filename,
		"status":           job.Status,
		"progress":         job.Progress,
		"total_frames":     job.TotalFrames,
		"processed_frames": job.ProcessedFrames,
		"error_message":    job.ErrorMessage,
		"created_at":       job.CreatedAt,
		"completed_at":     job.CompletedAt,
	})
}

func (s *Server) getVideoResult(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var job models.VideoJob
	if err := s.db.First(&job, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	if job.Status != "done" {
		c.JSON(http.StatusConflict, gin.H{"error": fmt.Sprintf("Job not done yet. Status: %s", job.Status)})
		return
	}

	var results []interface{}
	json.Unmarshal([]byte(job.ResultJSON), &results)

	c.JSON(http.StatusOK, gin.H{
		"job_id":                 job.ID,
		"filename":               job.Filename,
		"total_frames_processed": job.ProcessedFrames,
		"total_violation_frames": countViolationFrames(results),
		"frames":                 results,
	})
}

func (s *Server) deleteVideoJob(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var job models.VideoJob
	if err := s.db.First(&job, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
		return
	}

	// Delete file
	os.Remove(job.FilePath)

	// Delete record
	s.db.Delete(&job)

	c.JSON(http.StatusOK, gin.H{"status": "deleted", "id": id})
}

// ============================================================================
// WebSocket
// ============================================================================

func (s *Server) streamWebSocket(c *gin.Context) {
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("WebSocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	// TODO: Implement streaming loop
	// This would capture frames and send them with detection overlay
	for {
		_, msg, err := conn.ReadMessage()
		if err != nil {
			log.Printf("WebSocket read error: %v", err)
			break
		}
		// Handle incoming messages (e.g., ping)
		if string(msg) == "ping" {
			conn.WriteMessage(websocket.TextMessage, []byte("pong"))
		}
	}
}

func (s *Server) alertsWebSocket(c *gin.Context) {
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("WebSocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	// TODO: Implement real-time alerts
	for {
		_, msg, err := conn.ReadMessage()
		if err != nil {
			log.Printf("WebSocket read error: %v", err)
			break
		}
		if string(msg) == "ping" {
			conn.WriteMessage(websocket.TextMessage, []byte("pong"))
		}
	}
}

// ============================================================================
// Helpers
// ============================================================================

// base64Wrap wraps the standard library for use in this file
var stdEncoding = base64.NewEncoding("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")

func decodeBase64Image(data string) ([]byte, error) {
	// Handle data URL format
	if len(data) > 23 {
		if strings.HasPrefix(data, "data:image/jpeg;base64,") {
			data = strings.TrimPrefix(data, "data:image/jpeg;base64,")
		} else if strings.HasPrefix(data, "data:image/png;base64,") {
			data = strings.TrimPrefix(data, "data:image/png;base64,")
		} else if strings.HasPrefix(data, "data:image/jpg;base64,") {
			data = strings.TrimPrefix(data, "data:image/jpg;base64,")
		}
	}

	return stdEncoding.DecodeString(data)
}

func countViolationFrames(frames []interface{}) int {
	count := 0
	for _, f := range frames {
		if m, ok := f.(map[string]interface{}); ok {
			if hasViolation, _ := m["has_violation"].(bool); hasViolation {
				count++
			}
		}
	}
	return count
}
