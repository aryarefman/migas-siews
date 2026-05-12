package rtmp

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/yutopp/go-rtmp"
	"github.com/yutopp/go-rtmp/message"
)

// RTMPIngest handles RTMP stream ingestion
type RTMPIngest struct {
	server      *rtmp.Server
	frameChan   chan []byte
	done        chan struct{}
	mu          sync.Mutex
	running     bool
	config      *RTMPConfig
}

// RTMPConfig holds RTMP server configuration
type RTMPConfig struct {
	Port         string
	App          string
	EnableAuth   bool
	AuthUsername string
	AuthPassword string
}

// NewIngest creates a new RTMPIngest instance
func NewIngest() *RTMPIngest {
	return &RTMPIngest{
		frameChan: make(chan []byte, 100),
		done:      make(chan struct{}),
		config: &RTMPConfig{
			Port:       ":1935",
			App:        "live",
			EnableAuth: false,
		},
	}
}

// Start starts the RTMP server
func (r *RTMPIngest) Start(addr string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.running {
		return fmt.Errorf("RTMP server already running")
	}

	if addr != "" {
		r.config.Port = addr
	}

	// Create RTMP server
	r.server = rtmp.NewServer(&rtmp.ServerConfig{
		OnConnect: func(conn net.Conn) {
			log.Printf("RTMP: New connection from %s", conn.RemoteAddr())
		},
		HandlePlay: func(conn *rtmp.Conn) {
			log.Printf("RTMP: Play request from %s", conn.RemoteAddr())
			// Handle RTSP play (viewer)
		},
		HandlePublish: func(conn *rtmp.Conn) {
			log.Printf("RTMP: Publish request from %s", conn.RemoteAddr())
			r.handlePublish(conn)
		},
	})

	r.running = true
	log.Printf("RTMP: Server starting on %s", r.config.Port)

	// Start server in a goroutine
	go func() {
		if err := r.server.ListenAndServe(r.config.Port); err != nil {
			log.Printf("RTMP: Server error: %v", err)
			r.mu.Lock()
			r.running = false
			r.mu.Unlock()
		}
	}()

	return nil
}

// handlePublish handles RTMP publish requests
func (r *RTMPIngest) handlePublish(conn *rtmp.Conn) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("RTMP: Panic in handlePublish: %v", r)
		}
	}()

	frameNum := 0

	// Read messages from the connection
	for {
		select {
		case <-r.done:
			return
		default:
			msg, err := conn.ReadMessage()
			if err != nil {
				log.Printf("RTMP: Error reading message: %v", err)
				return
			}

			// Process different message types
			switch m := msg.(type) {
			case *message.VideoMessage:
				// Handle video data
				frameNum++
				log.Printf("RTMP: Received video frame %d (size: %d bytes)", frameNum, len(m.Payload))

				// In production, you would:
				// 1. Decode the video message
				// 2. Extract raw frame
				// 3. Send to frame channel
				// frameData := decodeVideoMessage(m)
				// select {
				// case r.frameChan <- frameData:
				// default:
				//     log.Println("RTMP: Frame buffer full, dropping frame")
				// }

			case *message.AudioMessage:
				// Handle audio data (optional)
				log.Printf("RTMP: Received audio message (size: %d bytes)", len(m.Payload))

			case *message.DataMessage:
				// Handle metadata
				log.Printf("RTMP: Received data message")

			default:
				log.Printf("RTMP: Unknown message type: %T", m)
			}
		}
	}
}

// GetFrameChannel returns the frame channel
func (r *RTMPIngest) GetFrameChannel() <-chan []byte {
	return r.frameChan
}

// SetConfig sets the RTMP configuration
func (r *RTMPIngest) SetConfig(config *RTMPConfig) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.config = config
}

// Stop stops the RTMP server
func (r *RTMPIngest) Stop() {
	r.mu.Lock()
	defer r.mu.Unlock()

	if !r.running {
		return
	}

	close(r.done)
	
	if r.server != nil {
		// Close the server (implementation depends on the library)
		log.Println("RTMP: Stopping server")
	}

	r.running = false
	log.Println("RTMP: Server stopped")
}

// IsRunning returns whether the RTMP server is running
func (r *RTMPIngest) IsRunning() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.running
}

// GetStats returns RTMP server statistics
func (r *RTMPIngest) GetStats() map[string]interface{} {
	r.mu.Lock()
	defer r.mu.Unlock()

	return map[string]interface{}{
		"running":  r.running,
		"port":     r.config.Port,
		"app":      r.config.App,
		"auth":     r.config.EnableAuth,
	}
}
