package buffer

import (
	"fmt"
	"log"
	"sync"
	"time"
)

// Frame represents a video frame with metadata
type Frame struct {
	Data      []byte
	Timestamp int64
	Source    string // "rtsp", "grpc", "rtmp"
	CameraID  string
	FrameNum  int32
}

// FrameBuffer is a ring buffer for efficient frame storage
type FrameBuffer struct {
	buffer     []*Frame
	head       int
	tail       int
	size       int
	capacity   int
	mu         sync.Mutex
	cond       *sync.Cond
	dropCount  int64
	pushCount  int64
	popCount   int64
}

// NewFrameBuffer creates a new frame buffer with the given capacity
func NewFrameBuffer(capacity int) *FrameBuffer {
	if capacity <= 0 {
		capacity = 100 // Default capacity
	}

	fb := &FrameBuffer{
		buffer:   make([]*Frame, capacity),
		capacity: capacity,
	}
	fb.cond = sync.NewCond(&fb.mu)

	return fb
}

// Push adds a frame to the buffer
func (fb *FrameBuffer) Push(data []byte, cameraID string, frameNum int32) error {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	// Check if buffer is full
	if fb.size == fb.capacity {
		// Drop oldest frame
		fb.dropOldest()
	}

	frame := &Frame{
		Data:      data,
		Timestamp: time.Now().UnixMicro(),
		Source:    "unknown",
		CameraID:  cameraID,
		FrameNum:  frameNum,
	}

	fb.buffer[fb.head] = frame
	fb.head = (fb.head + 1) % fb.capacity
	fb.size++

	fb.pushCount++

	// Signal waiting goroutines
	fb.cond.Signal()

	return nil
}

// PushWithSource adds a frame to the buffer with source information
func (fb *FrameBuffer) PushWithSource(data []byte, cameraID string, frameNum int32, source string) error {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	// Check if buffer is full
	if fb.size == fb.capacity {
		// Drop oldest frame
		fb.dropOldest()
	}

	frame := &Frame{
		Data:      data,
		Timestamp: time.Now().UnixMicro(),
		Source:    source,
		CameraID:  cameraID,
		FrameNum:  frameNum,
	}

	fb.buffer[fb.head] = frame
	fb.head = (fb.head + 1) % fb.capacity
	fb.size++

	fb.pushCount++

	// Signal waiting goroutines
	fb.cond.Signal()

	return nil
}

// Pop removes and returns the oldest frame from the buffer
func (fb *FrameBuffer) Pop() (*Frame, error) {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	if fb.size == 0 {
		return nil, fmt.Errorf("buffer is empty")
	}

	frame := fb.buffer[fb.tail]
	fb.buffer[fb.tail] = nil // Help GC
	fb.tail = (fb.tail + 1) % fb.capacity
	fb.size--

	fb.popCount++

	return frame, nil
}

// PopByCameraID removes and returns the oldest frame for a specific camera
func (fb *FrameBuffer) PopByCameraID(cameraID string) (*Frame, error) {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	if fb.size == 0 {
		return nil, fmt.Errorf("buffer is empty")
	}

	// Find the oldest frame for the specific camera
	for i := 0; i < fb.size; i++ {
		idx := (fb.tail + i) % fb.capacity
		frame := fb.buffer[idx]
		if frame != nil && frame.CameraID == cameraID {
			// Remove this frame by shifting
			for j := i; j < fb.size-1; j++ {
				currentIdx := (fb.tail + j) % fb.capacity
				nextIdx := (fb.tail + j + 1) % fb.capacity
				fb.buffer[currentIdx] = fb.buffer[nextIdx]
			}
			fb.buffer[(fb.tail + fb.size - 1) % fb.capacity] = nil
			fb.size--
			fb.popCount++
			return frame, nil
		}
	}

	return nil, fmt.Errorf("no frame found for camera %s", cameraID)
}

// PopWithTimeout waits for a frame with a timeout
func (fb *FrameBuffer) PopWithTimeout(timeout time.Duration) (*Frame, error) {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	// If buffer is not empty, return immediately
	if fb.size > 0 {
		frame := fb.buffer[fb.tail]
		fb.buffer[fb.tail] = nil
		fb.tail = (fb.tail + 1) % fb.capacity
		fb.size++
		fb.popCount++
		return frame, nil
	}

	// Wait for a frame or timeout
	done := make(chan struct{})
	go func() {
		fb.cond.Wait()
		close(done)
	}()

	select {
	case <-done:
		if fb.size == 0 {
			return nil, fmt.Errorf("buffer is empty")
		}
		frame := fb.buffer[fb.tail]
		fb.buffer[fb.tail] = nil
		fb.tail = (fb.tail + 1) % fb.capacity
		fb.size--
		fb.popCount++
		return frame, nil
	case <-time.After(timeout):
		return nil, fmt.Errorf("timeout waiting for frame")
	}
}

// Peek returns the oldest frame without removing it
func (fb *FrameBuffer) Peek() (*Frame, error) {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	if fb.size == 0 {
		return nil, fmt.Errorf("buffer is empty")
	}

	return fb.buffer[fb.tail], nil
}

// dropOldest removes the oldest frame from the buffer
func (fb *FrameBuffer) dropOldest() {
	if fb.size == 0 {
		return
	}

	fb.buffer[fb.tail] = nil
	fb.tail = (fb.tail + 1) % fb.capacity
	fb.size--
	fb.dropCount++

	log.Printf("FrameBuffer: Dropped frame (buffer full). Total dropped: %d", fb.dropCount)
}

// Clear removes all frames from the buffer
func (fb *FrameBuffer) Clear() {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	for i := 0; i < fb.capacity; i++ {
		fb.buffer[i] = nil
	}
	fb.head = 0
	fb.tail = 0
	fb.size = 0

	log.Println("FrameBuffer: Cleared all frames")
}

// Size returns the current number of frames in the buffer
func (fb *FrameBuffer) Size() int {
	fb.mu.Lock()
	defer fb.mu.Unlock()
	return fb.size
}

// Capacity returns the buffer capacity
func (fb *FrameBuffer) Capacity() int {
	return fb.capacity
}

// Stats returns buffer statistics
func (fb *FrameBuffer) Stats() map[string]interface{} {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	dropRate := 0.0
	if fb.pushCount > 0 {
		dropRate = float64(fb.dropCount) / float64(fb.pushCount) * 100
	}

	return map[string]interface{}{
		"size":       fb.size,
		"capacity":   fb.capacity,
		"push_count": fb.pushCount,
		"pop_count":  fb.popCount,
		"drop_count": fb.dropCount,
		"drop_rate":  fmt.Sprintf("%.2f%%", dropRate),
		"utilization": fmt.Sprintf("%.2f%%", float64(fb.size)/float64(fb.capacity)*100),
	}
}

// GetFramesByCameraID returns all frames for a specific camera
func (fb *FrameBuffer) GetFramesByCameraID(cameraID string) []*Frame {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	frames := make([]*Frame, 0)
	for i := 0; i < fb.size; i++ {
		idx := (fb.tail + i) % fb.capacity
		frame := fb.buffer[idx]
		if frame != nil && frame.CameraID == cameraID {
			frames = append(frames, frame)
		}
	}

	return frames
}

// GetOldestFrame returns the oldest frame in the buffer
func (fb *FrameBuffer) GetOldestFrame() *Frame {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	if fb.size == 0 {
		return nil
	}

	return fb.buffer[fb.tail]
}

// GetNewestFrame returns the newest frame in the buffer
func (fb *FrameBuffer) GetNewestFrame() *Frame {
	fb.mu.Lock()
	defer fb.mu.Unlock()

	if fb.size == 0 {
		return nil
	}

	idx := (fb.head - 1 + fb.capacity) % fb.capacity
	return fb.buffer[idx]
}
