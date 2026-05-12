// Package camera provides camera capture functionality via Python inference service
package camera

import (
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

// Camera represents a video capture device (proxy to Python service)
type Camera struct {
	deviceID     int
	running      bool
	mu           sync.Mutex
	inferenceURL string
	httpClient   *http.Client
}

// NewCamera creates a new camera instance that proxies to Python inference service
func NewCamera(deviceID int) (*Camera, error) {
	// Try to start webcam via Python inference service
	inferenceURL := "http://localhost:8001"

	cam := &Camera{
		deviceID:     deviceID,
		running:      true,
		inferenceURL: inferenceURL,
		httpClient: &http.Client{
			Timeout: 5 * time.Second,
		},
	}

	// Try to start webcam
	resp, err := cam.httpClient.Get(inferenceURL + "/webcam/start")
	if err != nil {
		return cam, fmt.Errorf("webcam start failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return cam, fmt.Errorf("webcam start returned status: %d", resp.StatusCode)
	}

	return cam, nil
}

// Read reads a frame from the camera via Python inference service
func (c *Camera) Read() ([]byte, error) {
	if !c.running {
		return nil, fmt.Errorf("camera not running")
	}

	resp, err := c.httpClient.Get(c.inferenceURL + "/webcam/frame")
	if err != nil {
		return nil, fmt.Errorf("failed to get frame: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("frame request returned status: %d", resp.StatusCode)
	}

	// Read response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read frame: %w", err)
	}

	return body, nil
}

// Close closes the camera
func (c *Camera) Close() {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.running = false
	c.httpClient.Get(c.inferenceURL + "/webcam/stop")
}

// IsRunning returns whether the camera is running
func (c *Camera) IsRunning() bool {
	return c.running
}

// GetStreamURL returns the MJPEG stream URL from Python inference service
func (c *Camera) GetStreamURL() string {
	return c.inferenceURL + "/stream"
}
