# Camera Gateway - gRPC Bidirectional Streaming + RTSP/RTMP

Camera communication layer for SIEWS+ system using gRPC bidirectional streaming for near real-time camera-to-server communication and RTSP/RTMP for camera input.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Camera Sources                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ IP Camera    │  │ USB Camera   │  │ RTMP Stream  │        │
│  │ (RTSP)       │  │ (gRPC Client)│  │ (OBS/Encoder)│        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼─────────────────┼─────────────────┼──────────────────┘
          │                 │                 │
          │ RTSP            │ gRPC            │ RTMP
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              Camera Gateway Service                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ RTSP Ingest  │  │ gRPC Server  │  │ RTMP Ingest  │        │
│  │ (gortsplib)  │  │ (Bidirectional│  │ (go-rtmp)    │        │
│  │              │  │  Streaming)  │  │              │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼─────────────────┼─────────────────┼──────────────────┘
          │                 │                 │
          │                 ▼                 │
          │        ┌────────────────┐        │
          │        │ Frame Buffer   │        │
          │        │ & Queue        │        │
          │        └────────┬───────┘        │
          │                 │                │
          └─────────────────┼────────────────┘
                            │
                            │ Raw Frames
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Detection Pipeline                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Frame        │  │ YOLO         │  │ Annotated    │        │
│  │ Decoder      │  │ Inference    │  │ Frame        │        │
│  │ (H.264/H.265)│  │ (ONNX)       │  │ Generator    │        │
│  └──────────────┘  └──────────────┘  └──────┬───────┘        │
└────────────────────────────────────────────────┼──────────────┘
                                                   │
                            ┌──────────────────────┼──────────────────────┐
                            │                      │                      │
                            ▼                      ▼                      ▼
                   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
                   │ gRPC Response│      │ RTSP Server  │      │ WebSocket    │
                   │ (to Client)  │      │ (to Viewers) │      │ (to Browser) │
                   └──────────────┘      └──────────────┘      └──────────────┘
```

## Project Structure

```
camera-gateway/
├── proto/
│   └── camera.proto              # gRPC protocol definitions
├── cmd/
│   ├── gateway/
│   │   └── main.go               # Main gateway service
│   ├── rtsp-ingest/
│   │   └── main.go               # RTSP ingest service
│   └── rtmp-ingest/
│       └── main.go               # RTMP ingest service
├── internal/
│   ├── grpc/
│   │   ├── server.go             # gRPC server implementation
│   │   └── client.go             # gRPC client implementation
│   ├── rtsp/
│   │   └── ingest.go             # RTSP ingest implementation
│   ├── rtmp/
│   │   └── ingest.go             # RTMP ingest implementation
│   ├── buffer/
│   │   └── frame_buffer.go       # Frame buffer implementation
│   └── detection/
│       └── pipeline.go           # YOLO detection pipeline
├── pkg/
│   └── models/
│       └── camera.go             # Camera data models
├── go.mod
└── README.md
```

## Technology Stack

- **gRPC**: grpc-go (google.golang.org/grpc)
- **WebSocket**: gorilla/websocket (github.com/gorilla/websocket)
- **RTSP**: gortsplib (github.com/bluenviron/gortsplib)
- **RTMP**: go-rtmp (github.com/yutopp/go-rtmp)
- **ONNX Runtime**: onnxruntime-go (github.com/yalue/onnxruntime_go)
- **Database**: GORM (gorm.io/gorm) + go-sqlite3

## Setup

### Prerequisites

- Go 1.21 or higher
- Protocol Buffers compiler (protoc)
- gRPC plugins for Go

### Installation

1. Clone the repository:
```bash
cd /mnt/f/migas-siews/camera-gateway
```

2. Install dependencies:
```bash
go mod download
```

3. Generate Go code from protobuf:
```bash
protoc --go_out=. --go-grpc_out=. proto/camera.proto
```

4. Build the services:
```bash
go build -o bin/gateway cmd/gateway/main.go
go build -o bin/rtsp-ingest cmd/rtsp-ingest/main.go
go build -o bin/rtmp-ingest cmd/rtmp-ingest/main.go
```

## Configuration

### Environment Variables

```bash
# gRPC Server
GRPC_PORT=50051
GRPC_MAX_CONCURRENT_STREAMS=100

# RTSP Ingest
RTSP_SOURCES=rtsp://camera1:554/stream,rtsp://camera2:554/stream
RTSP_AUTH_USERNAME=admin
RTSP_AUTH_PASSWORD=password

# RTMP Server
RTMP_PORT=1935
RTMP_APP=live

# Frame Buffer
BUFFER_SIZE=100
FRAME_DROP_STRATEGY=oldest

# Detection
MODEL_PATH=/models/yolov8n.onnx
CONFIDENCE_THRESHOLD=0.5
DETECTION_INTERVAL=3
```

## Running the Services

### Gateway Service

```bash
go run cmd/gateway/main.go
```

### RTSP Ingest Service

```bash
go run cmd/rtsp-ingest/main.go
```

### RTMP Ingest Service

```bash
go run cmd/rtmp-ingest/main.go
```

## gRPC API

### Bidirectional Streaming

The `StreamFrames` RPC enables real-time two-way communication between camera clients and the server.

**Request Message:**
```protobuf
message FrameRequest {
  bytes frame_data = 1;        // Raw frame bytes (JPEG/H.264)
  int64 timestamp = 2;         // Unix timestamp in microseconds
  string camera_id = 3;        // Camera identifier
  int32 frame_number = 4;      // Sequential frame number
  map<string, string> metadata = 5; // Optional metadata
}
```

**Response Message:**
```protobuf
message FrameResponse {
  bytes annotated_frame = 1;    // Frame with detection overlay
  repeated Detection detections = 2; // Detection results
  int64 processing_time_us = 3; // Processing time in microseconds
  string status = 4;            // "ok", "error", etc.
  string error_message = 5;     // Error details if any
}
```

## Performance Targets

- **Latency**: < 100ms from frame ingest to detection response
- **Throughput**: Support 10+ concurrent cameras at 30 FPS
- **Frame Drop Rate**: < 1% under normal load
- **Memory Usage**: < 2GB for 10 cameras
- **CPU Usage**: < 80% on 4-core system for 10 cameras

## Development Status

### Phase 1: Project Setup & Protocol Definition ✅
- [x] Project structure created
- [x] Protocol buffer definitions
- [x] Go module initialized
- [x] Dependencies defined
- [x] Basic implementations created

### Phase 2: gRPC Bidirectional Streaming (In Progress)
- [ ] Complete gRPC server implementation
- [ ] Complete gRPC client implementation
- [ ] Generate protobuf Go code
- [ ] Unit tests
- [ ] Performance benchmarks

### Phase 3: RTSP Ingest Service (Pending)
- [ ] Complete RTSP client implementation
- [ ] Frame decoding integration
- [ ] Testing with real cameras

### Phase 4: RTMP Ingest Service (Pending)
- [ ] Complete RTMP server implementation
- [ ] Frame extraction
- [ ] Testing with OBS/FFmpeg

### Phase 5: Frame Buffer & Detection Integration (Pending)
- [ ] Complete frame buffer implementation
- [ ] ONNX model integration
- [ ] Multi-output routing

### Phase 6: Testing & Optimization (Pending)
- [ ] End-to-end testing
- [ ] Performance optimization
- [ ] Documentation

## Integration with SIEWS+

This camera gateway is designed to integrate with the existing SIEWS+ system:

1. **REST API Compatibility**: Maintain existing REST endpoints for zones, alerts, settings
2. **WebSocket Protocol**: Compatible with existing WebSocket alert system
3. **Database**: Uses same SQLite database schema
4. **Frontend**: Minimal changes required, can consume RTSP/WebSocket streams

## Troubleshooting

### gRPC Connection Issues
- Check if port 50051 is available
- Verify firewall settings
- Check logs for connection errors

### RTSP Connection Issues
- Verify RTSP URL format
- Check authentication credentials
- Ensure camera is accessible from network

### ONNX Model Loading
- Verify model path is correct
- Check ONNX model format compatibility
- Ensure ONNX Runtime is properly initialized

## License

This is part of the SIEWS+ project.
