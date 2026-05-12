package grpc

import (
	"context"
	"encoding/base64"
	"fmt"
	"io"
	"log"
	"time"

	// pb "camera-gateway/proto" // Will be uncommented after proto generation
)

// CameraClient implements the gRPC client for camera streaming
type CameraClient struct {
	// client pb.CameraStreamClient
	cameraID string
}

// NewCameraClient creates a new CameraClient instance
func NewCameraClient(addr string, cameraID string) (*CameraClient, error) {
	// TODO: Implement after proto generation
	// conn, err := grpc.Dial(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	// if err != nil {
	//     return nil, err
	// }
	
	// client := pb.NewCameraStreamClient(conn)
	
	return &CameraClient{
		// client: client,
		cameraID: cameraID,
	}, nil
}

// StreamFrames starts a bidirectional stream for sending frames and receiving responses
func (c *CameraClient) StreamFrames(frameData []byte, frameNum int32) ([]byte, error) {
	// TODO: Implement after proto generation
	log.Printf("Sending frame %d from camera %s", frameNum, c.cameraID)
	
	// stream, err := c.client.StreamFrames(context.Background())
	// if err != nil {
	//     return nil, err
	// }
	
	// req := &pb.FrameRequest{
	//     FrameData:   frameData,
	//     Timestamp:   time.Now().UnixMicro(),
	//     CameraId:    c.cameraID,
	//     FrameNumber: frameNum,
	// }
	
	// if err := stream.Send(req); err != nil {
	//     return nil, err
	// }
	
	// resp, err := stream.Recv()
	// if err != nil {
	//     return nil, err
	// }
	
	// return resp.AnnotatedFrame, nil
	
	// Placeholder for now
	return frameData, nil
}

// SendTestFrame sends a test frame (for testing purposes)
func (c *CameraClient) SendTestFrame() error {
	// Create a simple test frame (base64 encoded dummy data)
	testData := []byte("test_frame_data")
	
	_, err := c.StreamFrames(testData, 1)
	return err
}

// Close closes the client connection
func (c *CameraClient) Close() error {
	// TODO: Implement after proto generation
	return nil
}

// SimulateCameraClient simulates a camera client for testing
type SimulateCameraClient struct {
	cameraID string
	fps      int
	frameNum int32
	running  bool
}

// NewSimulateCameraClient creates a new simulated camera client
func NewSimulateCameraClient(cameraID string, fps int) *SimulateCameraClient {
	return &SimulateCameraClient{
		cameraID: cameraID,
		fps:      fps,
		frameNum: 0,
		running:  false,
	}
}

// Start starts the simulated camera
func (c *SimulateCameraClient) Start(duration time.Duration) {
	c.running = true
	ticker := time.NewTicker(time.Duration(1000/c.fps) * time.Millisecond)
	defer ticker.Stop()
	
	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()
	
	log.Printf("Starting simulated camera %s at %d FPS for %v", c.cameraID, c.fps, duration)
	
	for {
		select {
		case <-ctx.Done():
			c.running = false
			log.Printf("Simulated camera %s stopped", c.cameraID)
			return
		case <-ticker.C:
			c.frameNum++
			// Simulate sending a frame
			frameData := c.generateTestFrame()
			
			// TODO: Send to actual gRPC server when implemented
			log.Printf("Simulated camera %s: sent frame %d (size: %d bytes)", 
				c.cameraID, c.frameNum, len(frameData))
		}
	}
}

// Stop stops the simulated camera
func (c *SimulateCameraClient) Stop() {
	c.running = false
}

// generateTestFrame generates a test frame (placeholder)
func (c *SimulateCameraClient) generateTestFrame() []byte {
	// In a real implementation, this would capture from a camera or read from a file
	// For now, return dummy data
	data := fmt.Sprintf("frame_%d_from_%s", c.frameNum, c.cameraID)
	return []byte(base64.StdEncoding.EncodeToString([]byte(data)))
}
