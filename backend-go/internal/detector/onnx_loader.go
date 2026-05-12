package detector

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
)

// ============================================================================
// Model Configuration
// ============================================================================

// ModelConfig holds configuration for a detection model
type ModelConfig struct {
	Name          string
	Path          string
	Conf          float32
	Classes       map[int]string
	IsEnabled     bool
	FallbackModel string
}

// Model classes definitions

// PPE Classes (Stage 2) - labeled_safety dataset
var PPEClasses = map[int]string{
	0: "unknown",
	1: "belt",
	2: "helmet",
	3: "vest",
}

// Environment Classes (Stage 3) - open hole / construction safety
var EnvClasses = map[int]string{
	0: "barricade",
	1: "hard-hat",
	2: "safety-cone",
	3: "open-hole",
	4: "vest",
}

// Infrastructure Classes (Stage 4)
var InfraClasses = map[int]string{
	0: "oil_storage_tank",
	1: "oil_tank_truck",
	2: "construction_equip",
	3: "open_hole",
	4: "pressure_gauge",
	5: "adr_plate",
	6: "truck",
	7: "cctv_anomaly",
}

// Road Damage Classes (Stage 5) - jalan berlubang
var RoadClasses = map[int]string{
	0: "lubang",
	1: "retak",
	2: "tambalan",
}

// COCO Person classes for Stage 1 (YOLO uses class 0 for person)
var PersonClasses = map[int]string{
	0: "person",
}

// ============================================================================
// ONNX Model Loader
// ============================================================================

// ONNXModel wraps ONNX Runtime model for inference
type ONNXModel struct {
	config ModelConfig
}

// NewONNXModel loads an ONNX model from the specified path
func NewONNXModel(config ModelConfig) (*ONNXModel, error) {
	absPath, err := filepath.Abs(config.Path)
	if err != nil {
		return nil, fmt.Errorf("invalid model path: %w", err)
	}

	// Check if file exists
	if _, err := os.Stat(absPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("model file not found: %s", absPath)
	}

	log.Printf("[DETECTOR] Loaded model config: %s from %s (conf=%.2f)", config.Name, absPath, config.Conf)

	return &ONNXModel{
		config: config,
	}, nil
}

// GetName returns the model name
func (m *ONNXModel) GetName() string {
	return m.config.Name
}

// GetClasses returns the class mapping
func (m *ONNXModel) GetClasses() map[int]string {
	return m.config.Classes
}

// ============================================================================
// Detection Result
// ============================================================================

// Detection represents a single detection result
type Detection struct {
	ClassID    int
	ClassName  string
	Confidence float32
	BBox       [4]int // [x1, y1, x2, y2] in pixel coordinates
}

// ============================================================================
// Model Paths
// ============================================================================

// GetModelPaths returns the paths to all model files
func GetModelPaths() map[string]string {
	// Model paths relative to backend directory
	baseDir := os.Getenv("MODELS_DIR")
	if baseDir == "" {
		baseDir = "../../backend/models"
	}

	paths := map[string]string{
		"stage1": filepath.Join(baseDir, "yolo26n.pt"),
		"stage2": filepath.Join(baseDir, "New/best_stage2_labeled_safety.pt"),
		"stage3": filepath.Join(baseDir, "New/best_stage3_openhole.pt"),
		"stage5": filepath.Join(baseDir, "New/best_jalan_berlubang.pt"),
	}

	return paths
}

// GetStageConfig returns the configuration for each stage
func GetStageConfig() map[string]ModelConfig {
	paths := GetModelPaths()

	return map[string]ModelConfig{
		"stage1": {
			Name:          "Person Detection",
			Path:          paths["stage1"],
			Conf:          0.35,
			Classes:       PersonClasses,
			IsEnabled:     true,
			FallbackModel: "yolo26n.pt",
		},
		"stage2": {
			Name:          "PPE Detection",
			Path:          paths["stage2"],
			Conf:          0.30,
			Classes:       PPEClasses,
			IsEnabled:     true,
			FallbackModel: "yolo26n.pt",
		},
		"stage3": {
			Name:          "Environment Detection",
			Path:          paths["stage3"],
			Conf:          0.35,
			Classes:       EnvClasses,
			IsEnabled:     true,
			FallbackModel: "yolo26n.pt",
		},
		"stage5": {
			Name:          "Road Damage Detection",
			Path:          paths["stage5"],
			Conf:          0.30,
			Classes:       RoadClasses,
			IsEnabled:     true,
			FallbackModel: "yolo26n.pt",
		},
	}
}
