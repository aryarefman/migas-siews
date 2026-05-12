package detector

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ============================================================================
// Inference Client - Calls Python Inference Service
// ============================================================================

// InferenceClient calls the Python inference service
type InferenceClient struct {
	baseURL    string
	httpClient *http.Client
}

// NewInferenceClient creates a new inference client
func NewInferenceClient(baseURL string) *InferenceClient {
	return &InferenceClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// DetectionRequest sent to Python service
// Uses snake_case to match Python FastAPI endpoints
type DetectionRequest struct {
	ImageB64 string   `json:"image_b64"` // snake_case for Python compatibility
	Stages   []string `json:"stages"`
}

// DetectionResponse from Python service
type DetectionResponse struct {
	Persons []PersonDetection `json:"persons"`
	Env     []EnvDetection    `json:"env"`
	Road    []RoadDetection   `json:"road"`
}

// PersonDetection represents a person detection result - matches Python backend format
type PersonDetection struct {
	BBox       []int             `json:"bbox"`
	Confidence float64            `json:"confidence"`
	Violations []string           `json:"violations"`
	PPEStatus  map[string]float64 `json:"ppe_status"`
}

// EnvDetection represents an environment detection result - matches Python backend format
type EnvDetection struct {
	Label      string  `json:"label"`
	Confidence float64 `json:"confidence"`
	BBox       []int   `json:"bbox"`
}

// RoadDetection represents a road damage detection result - matches Python backend format
type RoadDetection struct {
	Label      string  `json:"label"`
	Confidence float64 `json:"confidence"`
	BBox       []int   `json:"bbox"`
}

// Detect calls the Python inference service for detection
func (c *InferenceClient) Detect(imageData []byte, stages []string) (*DetectionResponse, error) {
	// Encode image to base64
	imageB64 := base64.StdEncoding.EncodeToString(imageData)

	req := DetectionRequest{
		ImageB64: imageB64,
		Stages:   stages,
	}

	reqBody, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	resp, err := c.httpClient.Post(
		c.baseURL+"/detect",
		"application/json",
		bytes.NewReader(reqBody),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to call inference service: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("inference service returned %d: %s", resp.StatusCode, string(body))
	}

	var result DetectionResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// AnalyzeImageResponse from analyze/image endpoint
type AnalyzeImageResponse struct {
	AnnotatedImage string `json:"annotated_image"`
	ImageSize      struct {
		Width  int `json:"width"`
		Height int `json:"height"`
	} `json:"image_size"`
	Detections struct {
		Persons         []PersonDetection `json:"persons"`
		Env             []EnvDetection    `json:"env"`
		Road            []RoadDetection   `json:"road"`
		TotalPersons    int               `json:"total_persons"`
		TotalEnv        int               `json:"total_env"`
		TotalRoad       int               `json:"total_road"`
		ViolationsFound bool              `json:"violations_found"`
	} `json:"detections"`
}

// AnalyzeImageRequest for the Python endpoint that expects "image" field
type AnalyzeImageRequest struct {
	ImageB64 string `json:"image_b64"` // Must match Python's DetectionRequest
	Stages   []string `json:"stages"`
}

// AnalyzeImage calls the Python analyze/image endpoint
func (c *InferenceClient) AnalyzeImage(imageData []byte) (*AnalyzeImageResponse, error) {
	// Encode image to base64
	imageB64 := base64.StdEncoding.EncodeToString(imageData)

	// Python endpoint expects "image_b64" field
	req := AnalyzeImageRequest{
		ImageB64: imageB64,
		Stages:   []string{"s1", "s2", "s3", "s5"},
	}

	reqBody, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	resp, err := c.httpClient.Post(
		c.baseURL+"/analyze/image",
		"application/json",
		bytes.NewReader(reqBody),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to call inference service: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("inference service returned %d: %s", resp.StatusCode, string(body))
	}

	var result AnalyzeImageResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// Health checks if the inference service is available
func (c *InferenceClient) Health() error {
	resp, err := c.httpClient.Get(c.baseURL + "/health")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed: %d", resp.StatusCode)
	}

	return nil
}
