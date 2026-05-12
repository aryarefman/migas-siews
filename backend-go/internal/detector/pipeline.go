package detector

import (
	"fmt"
	"log"
	"os"
	"sync"
	"time"

	"github.com/aryarefman/migas-siews/backend-go/internal/camera"
	"gorm.io/gorm"
)

// ============================================================================
// Multi-Stage Detection Pipeline
// ============================================================================

// Pipeline manages the multi-stage detection pipeline
type Pipeline struct {
	camera        *camera.Camera
	inference     *InferenceClient
	db            *gorm.DB
	mu            sync.RWMutex
	running       bool
	stagesEnabled map[string]bool
	confidence    float32
	ppeConfidence float32
	lastPersons   []PersonDetection
	lastEnv       []EnvDetection
	lastRoad      []RoadDetection
	cooldown      map[string]time.Time
}

// NewPipeline creates a new detection pipeline
func NewPipeline(db *gorm.DB) (*Pipeline, error) {
	// Open camera
	cam, err := camera.NewCamera(0)
	if err != nil {
		log.Printf("Warning: Failed to open camera: %v (continuing without camera)", err)
		cam = nil
	}

	// Initialize inference client (Python service)
	inferenceURL := "http://localhost:8001"
	if url := os.Getenv("INFERENCE_URL"); url != "" {
		inferenceURL = url
	}
	inference := NewInferenceClient(inferenceURL)

	// Check health
	if err := inference.Health(); err != nil {
		log.Printf("Warning: Inference service not available at %s: %v", inferenceURL, err)
		log.Println("Running in standalone mode - inference will be disabled")
	} else {
		log.Println("Inference service connected")
	}

	return &Pipeline{
		camera:    cam,
		inference: inference,
		db:        db,
		running:   true,
		stagesEnabled: map[string]bool{
			"stage1": true, // Person
			"stage2": true, // PPE
			"stage3": true, // Environment
			"stage5": true, // Road damage
		},
		confidence:    0.35,
		ppeConfidence: 0.30,
		cooldown:      make(map[string]time.Time),
	}, nil
}

// Close closes the pipeline and releases resources
func (p *Pipeline) Close() {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.running = false
	if p.camera != nil {
		p.camera.Close()
	}
}

// IsRunning returns whether the pipeline is running
func (p *Pipeline) IsRunning() bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.running
}

// EnableStage enables a detection stage
func (p *Pipeline) EnableStage(stage string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.stagesEnabled[stage] = true
}

// DisableStage disables a detection stage
func (p *Pipeline) DisableStage(stage string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.stagesEnabled[stage] = false
}

// IsStageEnabled checks if a stage is enabled
func (p *Pipeline) IsStageEnabled(stage string) bool {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.stagesEnabled[stage]
}

// SetConfidence sets the detection confidence threshold
func (p *Pipeline) SetConfidence(conf float32) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.confidence = conf
}

// SetPPEConfidence sets the PPE detection confidence threshold
func (p *Pipeline) SetPPEConfidence(conf float32) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.ppeConfidence = conf
}

// ============================================================================
// Frame Processing
// ============================================================================

// DetectionResult contains the combined detection results
type DetectionResult struct {
	Persons []PersonDetection `json:"persons"`
	Env     []EnvDetection    `json:"env"`
	Road    []RoadDetection   `json:"road"`
}

// ProcessFrame captures a frame and runs detection
func (p *Pipeline) ProcessFrame() ([]byte, *DetectionResult, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	if !p.running {
		return nil, nil, fmt.Errorf("pipeline not running")
	}

	var frameData []byte
	var err error

	// Capture frame from camera
	if p.camera != nil {
		frameData, err = p.camera.Read()
		if err != nil {
			return nil, nil, fmt.Errorf("failed to capture frame: %w", err)
		}
	}

	// Run detection
	result, err := p.Run(frameData)
	if err != nil {
		return frameData, nil, err
	}

	return frameData, result, nil
}

// Run runs the detection pipeline on a frame
func (p *Pipeline) Run(frameData []byte) (*DetectionResult, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	// Check if inference service is available
	if p.inference == nil {
		return &DetectionResult{
			Persons: []PersonDetection{},
			Env:     []EnvDetection{},
			Road:    []RoadDetection{},
		}, nil
	}

	// Check if frame is empty
	if len(frameData) == 0 {
		return &DetectionResult{
			Persons: []PersonDetection{},
			Env:     []EnvDetection{},
			Road:    []RoadDetection{},
		}, nil
	}

	// Determine enabled stages
	stages := []string{}
	for stage, enabled := range p.stagesEnabled {
		if enabled {
			stages = append(stages, stage)
		}
	}

	// Call inference service
	response, err := p.inference.Detect(frameData, stages)
	if err != nil {
		log.Printf("Inference error: %v", err)
		return &DetectionResult{
			Persons: []PersonDetection{},
			Env:     []EnvDetection{},
			Road:    []RoadDetection{},
		}, err
	}

	// Update last results
	p.lastPersons = response.Persons
	p.lastEnv = response.Env
	p.lastRoad = response.Road

	return &DetectionResult{
		Persons: response.Persons,
		Env:     response.Env,
		Road:    response.Road,
	}, nil
}

// GetLastResults returns the last detection results
func (p *Pipeline) GetLastResults() *DetectionResult {
	p.mu.RLock()
	defer p.mu.RUnlock()

	return &DetectionResult{
		Persons: p.lastPersons,
		Env:     p.lastEnv,
		Road:    p.lastRoad,
	}
}

// ============================================================================
// Image Analysis (for /analyze/image endpoint)
// ============================================================================

// AnalyzeImage analyzes a single image and returns annotated image
func (p *Pipeline) AnalyzeImage(imageData []byte) (*AnalyzeImageResponse, error) {
	if p.inference == nil {
		return nil, fmt.Errorf("inference service not available")
	}

	return p.inference.AnalyzeImage(imageData)
}

// ============================================================================
// Violation Detection
// ============================================================================

// CheckCooldown checks if an alert is in cooldown period
func (p *Pipeline) CheckCooldown(zoneID int, violationType string, cooldownSec int) bool {
	key := fmt.Sprintf("%d_%s", zoneID, violationType)
	if lastAlert, exists := p.cooldown[key]; exists {
		if time.Since(lastAlert) < time.Duration(cooldownSec)*time.Second {
			return true
		}
	}
	return false
}

// SetCooldown sets the cooldown for a violation type
func (p *Pipeline) SetCooldown(zoneID int, violationType string) {
	key := fmt.Sprintf("%d_%s", zoneID, violationType)
	p.cooldown[key] = time.Now()
}

// ClearCooldown clears the cooldown for a violation type
func (p *Pipeline) ClearCooldown(zoneID int, violationType string) {
	key := fmt.Sprintf("%d_%s", zoneID, violationType)
	delete(p.cooldown, key)
}

// HasViolations checks if there are any violations in the results
func (p *Pipeline) HasViolations(result *DetectionResult) bool {
	// Check for PPE violations
	for _, person := range result.Persons {
		if len(person.Violations) > 0 {
			return true
		}
	}

	// Check for environment hazards
	if len(result.Env) > 0 {
		return true
	}

	return false
}

// ============================================================================
// Configuration
// ============================================================================

// GetStagesStatus returns the status of all detection stages
func (p *Pipeline) GetStagesStatus() map[string]bool {
	p.mu.RLock()
	defer p.mu.RUnlock()

	status := make(map[string]bool)
	for stage, enabled := range p.stagesEnabled {
		status[stage] = enabled
	}
	return status
}

// LoadSettings loads pipeline settings from database
func (p *Pipeline) LoadSettings() error {
	if p.db == nil {
		return nil
	}

	var confidence, ppeConf string
	var detectionInterval int

	row := p.db.Raw("SELECT value FROM settings WHERE key = 'confidence_threshold'").Scan(&confidence)
	if row.Error == nil && confidence != "" {
		p.confidence = parseFloat32(confidence)
	}

	row = p.db.Raw("SELECT value FROM settings WHERE key = 'ppe_confidence'").Scan(&ppeConf)
	if row.Error == nil && ppeConf != "" {
		p.ppeConfidence = parseFloat32(ppeConf)
	}

	row = p.db.Raw("SELECT value FROM settings WHERE key = 'detection_interval'").Scan(&detectionInterval)
	if row.Error == nil {
		// Update camera capture interval if needed
		_ = detectionInterval
	}

	return nil
}

func parseFloat32(s string) float32 {
	var f float32
	fmt.Sscanf(s, "%f", &f)
	return f
}
