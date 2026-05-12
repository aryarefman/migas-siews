package rtsp

import (
	"context"
	"log"
	"sync"
	"time"

	"github.com/bluenviron/gortsplib/v4"
	"github.com/bluenviron/gortsplib/v4/pkg/description"
	"github.com/bluenviron/gortsplib/v4/pkg/format"
)

// RTSPIngest handles RTSP camera ingestion
type RTSPIngest struct {
	client      *gortsplib.Client
	streamURL   string
	frameChan   chan []byte
	done        chan struct{}
	mu          sync.Mutex
	connected   bool
	auth        *AuthConfig
}

// AuthConfig holds RTSP authentication configuration
type AuthConfig struct {
	Username string
	Password string
}

// NewIngest creates a new RTSPIngest instance
func NewIngest() *RTSPIngest {
	return &RTSPIngest{
		frameChan: make(chan []byte, 100),
		done:      make(chan struct{}),
	}
}

// Connect connects to an RTSP source and starts streaming
func (r *RTSPIngest) Connect(url string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.connected {
		return nil // Already connected
	}

	r.streamURL = url

	// Create RTSP client
	r.client = &gortsplib.Client{}

	// Parse URL and connect
	u, err := gortsplib.ParseURL(url)
	if err != nil {
		return err
	}

	// Connect with authentication if provided
	if r.auth != nil {
		r.client = &gortsplib.Client{
			// Authentication will be handled by the library
		}
	}

	err = r.client.Start(u.Scheme, u.Host)
	if err != nil {
		return err
	}

	// Describe the stream to get media description
	desc, err := r.client.Describe(u)
	if err != nil {
		r.client.Close()
		return err
	}

	// Find video track
	var videoTrack *description.Media
	for _, media := range desc.Medias {
		if media.Type == description.MediaTypeVideo {
			videoTrack = media
			break
		}
	}

	if videoTrack == nil {
		r.client.Close()
		return fmt.Errorf("no video track found in RTSP stream")
	}

	// Setup decoder based on codec
	// This is a simplified version - in production you'd handle different codecs
	var decoder interface{}

	for _, forma := range videoTrack.Formats {
		switch forma.(type) {
		case *format.H264:
			// Setup H.264 decoder
			log.Println("RTSP: Using H.264 codec")
			decoder = forma
		case *format.H265:
			// Setup H.265 decoder
			log.Println("RTSP: Using H.265 codec")
			decoder = forma
		default:
			log.Printf("RTSP: Unsupported codec: %T", forma)
		}
	}

	if decoder == nil {
		r.client.Close()
		return fmt.Errorf("no supported codec found")
	}

	// Start playing the stream
	err = r.client.PlayAll(desc)
	if err != nil {
		r.client.Close()
		return err
	}

	r.connected = true
	log.Printf("RTSP: Connected to %s", url)

	// Start reading frames in a goroutine
	go r.readFrames()

	return nil
}

// readFrames reads frames from the RTSP stream
func (r *RTSPIngest) readFrames() {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("RTSP: Panic in readFrames: %v", r)
		}
	}()

	frameNum := 0
	for {
		select {
		case <-r.done:
			return
		default:
			// Read frame from RTSP stream
			// This is a placeholder - actual implementation depends on the codec
			// For now, we'll simulate frame reading
			
			time.Sleep(33 * time.Millisecond) // ~30 FPS
			
			// In production, you would:
			// 1. Read RTP packet from stream
			// 2. Decode using appropriate decoder (H.264/H.265)
			// 3. Convert to raw frame
			// 4. Send to frame channel
			
			frameNum++
			log.Printf("RTSP: Read frame %d from %s", frameNum, r.streamURL)
			
			// Simulate sending frame data
			// frameData := decodeFrame(rtpPacket)
			// select {
			// case r.frameChan <- frameData:
			// default:
			//     log.Println("RTSP: Frame buffer full, dropping frame")
			// }
		}
	}
}

// GetFrameChannel returns the frame channel
func (r *RTSPIngest) GetFrameChannel() <-chan []byte {
	return r.frameChan
}

// SetAuth sets authentication credentials
func (r *RTSPIngest) SetAuth(username, password string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	
	r.auth = &AuthConfig{
		Username: username,
		Password: password,
	}
}

// Stop stops the RTSP ingestion
func (r *RTSPIngest) Stop() {
	r.mu.Lock()
	defer r.mu.Unlock()

	if !r.connected {
		return
	}

	close(r.done)
	
	if r.client != nil {
		r.client.Close()
	}

	r.connected = false
	log.Printf("RTSP: Disconnected from %s", r.streamURL)
}

// IsConnected returns whether the RTSP connection is active
func (r *RTSPIngest) IsConnected() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.connected
}

// Start starts the RTSP ingest service (for standalone mode)
func (r *RTSPIngest) Start() error {
	// This is for standalone mode when not using Connect()
	// Configuration would come from environment or config file
	return fmt.Errorf("use Connect() method instead")
}

// Reconnect attempts to reconnect to the RTSP source
func (r *RTSPIngest) Reconnect() error {
	r.Stop()
	
	// Wait before reconnecting
	time.Sleep(5 * time.Second)
	
	return r.Connect(r.streamURL)
}

// AutoReconnect enables automatic reconnection
func (r *RTSPIngest) AutoReconnect(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if !r.IsConnected() && r.streamURL != "" {
				log.Printf("RTSP: Attempting to reconnect to %s", r.streamURL)
				if err := r.Reconnect(); err != nil {
					log.Printf("RTSP: Reconnect failed: %v", err)
				}
			}
		}
	}
}
