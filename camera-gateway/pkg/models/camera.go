package models

import (
	"time"
)

// Camera represents a camera source
type Camera struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Type        string    `json:"type"` // "rtsp", "rtmp", "grpc"
	URL         string    `json:"url"`
	Enabled     bool      `json:"enabled"`
	Connected   bool      `json:"connected"`
	LastSeen    time.Time `json:"last_seen"`
	FPS         int       `json:"fps"`
	Resolution  string    `json:"resolution"`
	Codec       string    `json:"codec"`
	Auth        *AuthInfo `json:"auth,omitempty"`
	Config      CameraConfig `json:"config"`
}

// AuthInfo holds authentication information
type AuthInfo struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// CameraConfig holds camera-specific configuration
type CameraConfig struct {
	Width              int    `json:"width"`
	Height             int    `json:"height"`
	FrameRate          int    `json:"frame_rate"`
	Quality            int    `json:"quality"` // 1-100
	Bitrate            int    `json:"bitrate"`
	EnableDetection    bool   `json:"enable_detection"`
	DetectionInterval  int    `json:"detection_interval"`
	ConfidenceThreshold float32 `json:"confidence_threshold"`
}

// StreamStats represents statistics for a camera stream
type StreamStats struct {
	CameraID        string    `json:"camera_id"`
	FramesReceived  int64     `json:"frames_received"`
	FramesProcessed int64     `json:"frames_processed"`
	FramesDropped   int64     `json:"frames_dropped"`
	AvgLatencyMs    float64   `json:"avg_latency_ms"`
	CurrentFPS      float64   `json:"current_fps"`
	LastFrameTime   time.Time `json:"last_frame_time"`
	Uptime          time.Duration `json:"uptime"`
}

// DetectionResult represents a detection result from a frame
type DetectionResult struct {
	CameraID     string       `json:"camera_id"`
	FrameNumber  int32        `json:"frame_number"`
	Timestamp    time.Time    `json:"timestamp"`
	Detections   []Detection  `json:"detections"`
	AnnotatedURL string       `json:"annotated_url,omitempty"`
	ProcessingMs float64      `json:"processing_ms"`
}

// Detection represents a single object detection
type Detection struct {
	ClassName  string            `json:"class_name"`
	Confidence float32           `json:"confidence"`
	BBox       []int32           `json:"bbox"` // [x1, y1, x2, y2]
	Attributes map[string]float32 `json:"attributes,omitempty"`
}

// Alert represents a security alert
type Alert struct {
	ID          string       `json:"id"`
	CameraID    string       `json:"camera_id"`
	Type        string       `json:"type"` // "person", "fire", "ppe_violation", etc.
	Severity    string       `json:"severity"` // "low", "medium", "high"
	Timestamp   time.Time    `json:"timestamp"`
	Detection   Detection    `json:"detection"`
	SnapshotURL string       `json:"snapshot_url"`
	Resolved    bool         `json:"resolved"`
}

// CameraStatus represents the current status of a camera
type CameraStatus struct {
	CameraID     string    `json:"camera_id"`
	Status       string    `json:"status"` // "online", "offline", "error"
	Message      string    `json:"message"`
	LastUpdate   time.Time `json:"last_update"`
	Stats        StreamStats `json:"stats"`
}

// NewCamera creates a new Camera instance
func NewCamera(id, name, cameraType, url string) *Camera {
	return &Camera{
		ID:         id,
		Name:       name,
		Type:       cameraType,
		URL:        url,
		Enabled:    true,
		Connected:  false,
		LastSeen:   time.Time{},
		Config: CameraConfig{
			Width:             1920,
			Height:            1080,
			FrameRate:         30,
			Quality:           85,
			EnableDetection:   true,
			DetectionInterval: 3,
			ConfidenceThreshold: 0.5,
		},
	}
}

// UpdateStats updates the stream statistics
func (s *StreamStats) UpdateStats(framesReceived, framesProcessed, framesDropped int64, latencyMs float64) {
	s.FramesReceived += framesReceived
	s.FramesProcessed += framesProcessed
	s.FramesDropped += framesDropped
	
	// Calculate average latency
	if s.FramesProcessed > 0 {
		s.AvgLatencyMs = (s.AvgLatencyMs*float64(s.FramesProcessed-1) + latencyMs) / float64(s.FramesProcessed)
	}
	
	s.LastFrameTime = time.Now()
	
	// Calculate current FPS (frames in last second)
	if !s.LastFrameTime.IsZero() {
		elapsed := time.Since(s.LastFrameTime).Seconds()
		if elapsed > 0 {
			s.CurrentFPS = float64(framesReceived) / elapsed
		}
	}
}

// GetUptime returns the uptime of the stream
func (s *StreamStats) GetUptime() time.Duration {
	if s.LastFrameTime.IsZero() {
		return 0
	}
	return time.Since(s.LastFrameTime)
}

// IsHealthy returns whether the stream is healthy
func (s *StreamStats) IsHealthy() bool {
	if s.CurrentFPS < 1.0 {
		return false
	}
	if s.FramesDropped > s.FramesReceived/10 { // More than 10% drop rate
		return false
	}
	return true
}
