package grpc

import (
	"context"
	"fmt"
	"io"
	"log"
	"sync"
	"time"

	// pb "camera-gateway/proto" // Will be uncommented after proto generation
)

// CameraServer implements the gRPC server for camera streaming
type CameraServer struct {
	// pb.UnimplementedCameraStreamServer
	
	mu              sync.Mutex
	activeStreams   map[string]*StreamContext
	frameBuffer     FrameBuffer // To be implemented
	detectionPipeline DetectionPipeline // To be implemented
}

type StreamContext struct {
	CameraID    string
	StartTime   time.Time
	FramesRecv  int64
	FramesSent  int64
	LastFrame   time.Time
}

type FrameBuffer interface {
	Push(frame []byte, cameraID string, frameNum int32) error
	Pop(cameraID string) ([]byte, error)
}

type DetectionPipeline interface {
	ProcessFrame(frame []byte) ([]Detection, []byte, error)
}

type Detection struct {
	ClassName  string
	Confidence float32
	BBox       []int32
	Attributes map[string]float32
}

// NewCameraServer creates a new CameraServer instance
func NewCameraServer() *CameraServer {
	return &CameraServer{
		activeStreams: make(map[string]*StreamContext),
	}
}

// StreamFrames implements bidirectional streaming for camera frames
func (s *CameraServer) StreamFrames(stream interface{}) error {
	// TODO: Replace with actual gRPC stream type after proto generation
	// For now, this is a placeholder for the implementation
	
	log.Println("New camera stream connection established")
	
	ctx := &StreamContext{
		StartTime: time.Now(),
	}
	
	// TODO: Extract camera ID from first message
	cameraID := "camera-001"
	ctx.CameraID = cameraID
	
	s.mu.Lock()
	s.activeStreams[cameraID] = ctx
	s.mu.Unlock()
	
	defer func() {
		s.mu.Lock()
		delete(s.activeStreams, cameraID)
		s.mu.Unlock()
		log.Printf("Camera stream closed: %s", cameraID)
	}()
	
	// Main streaming loop
	for {
		// TODO: Receive frame from client
		// req, err := stream.Recv()
		// if err == io.EOF {
		//     return nil
		// }
		// if err != nil {
		//     return err
		// }
		
		// TODO: Process frame
		startTime := time.Now()
		
		// detections, annotatedFrame, err := s.detectionPipeline.ProcessFrame(req.FrameData)
		// if err != nil {
		//     log.Printf("Detection error: %v", err)
		//     // Send error response
		//     continue
		// }
		
		// TODO: Send response
		// resp := &pb.FrameResponse{
		//     AnnotatedFrame: annotatedFrame,
		//     Detections: detectionsToProto(detections),
		//     ProcessingTimeUs: time.Since(startTime).Microseconds(),
		//     Status: "ok",
		// }
		
		// if err := stream.Send(resp); err != nil {
		//     return err
		// }
		
		// Update statistics
		ctx.FramesRecv++
		ctx.FramesSent++
		ctx.LastFrame = time.Now()
		
		// Simulate processing for now
		time.Sleep(10 * time.Millisecond)
	}
}

// ConfigureCamera handles camera configuration
func (s *CameraServer) ConfigureCamera(ctx context.Context, config interface{}) (interface{}, error) {
	// TODO: Implement after proto generation
	log.Printf("ConfigureCamera called")
	return nil, fmt.Errorf("not implemented yet")
}

// GetStatus returns camera status
func (s *CameraServer) GetStatus(ctx context.Context, req interface{}) (interface{}, error) {
	// TODO: Implement after proto generation
	log.Printf("GetStatus called")
	return nil, fmt.Errorf("not implemented yet")
}

// GetActiveStreams returns information about active streams
func (s *CameraServer) GetActiveStreams() map[string]*StreamContext {
	s.mu.Lock()
	defer s.mu.Unlock()
	
	result := make(map[string]*StreamContext)
	for k, v := range s.activeStreams {
		result[k] = v
	}
	return result
}

// SetFrameBuffer sets the frame buffer for the server
func (s *CameraServer) SetFrameBuffer(fb FrameBuffer) {
	s.frameBuffer = fb
}

// SetDetectionPipeline sets the detection pipeline
func (s *CameraServer) SetDetectionPipeline(dp DetectionPipeline) {
	s.detectionPipeline = dp
}
