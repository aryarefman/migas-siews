# SIEWS+ Backend Migration Plan: Python → Go

## Executive Summary

Migrate the entire backend from Python to Go for better performance, single-binary deployment, and easier maintenance. The Python inference service remains for YOLO model inference (via `ultralytics`), while all business logic, API handling, video processing, and orchestration moves to Go.

---

## Phase 1: Architecture Analysis

### Current State

```
┌─────────────────────────────────────────────────────────────────┐
│                         PYTHON BACKEND                           │
│  main.py (946 lines) - API routes, WebSocket, everything       │
│  stream.py (640 lines) - Camera, detection loop, violations     │
│  detector.py (246 lines) - YOLO wrapper                         │
│  video_processor.py - Video analysis (BROKEN - 0 frames)        │
│  face_manager.py - Face recognition                             │
│  ocr_engine.py - OCR text recognition                           │
│  notifier.py - WhatsApp notifications                           │
│  ... 20+ more modules                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓ calls
┌─────────────────────────────────────────────────────────────────┐
│                    INFERENCE SERVICE (Python)                    │
│  FastAPI + YOLO models                                          │
│  Runs on port 8001                                              │
│  Go backend proxies to this                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       GO BACKEND (Partially done)                │
│  Server structure ✓                                             │
│  Video routes ✓ (BUT STUBBED - just sleeps 2 seconds!)         │
│  Polygon/zone management ✓                                      │
│  Alert system ✓                                                 │
│  Detection - calls Python inference service                      │
│  WhatsApp notifications ✓                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      GO BACKEND (Final)                          │
│  Single binary, port 8080                                        │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  API Server  │  │   Streaming  │  │   Video      │           │
│  │  (Gin)       │  │   (MJPEG)   │  │   Processor  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Detection   │  │  Violation   │  │  Face/OCR   │           │
│  │  Pipeline    │  │  Checker     │  │  Client     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                              ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Python Inference Service (port 8001)         │   │
│  │              ONLY for YOLO model inference                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 2: Module-by-Module Migration

### Module Mapping

| Python Module | Go Module | Status | Notes |
|--------------|-----------|--------|-------|
| `main.py` | `internal/api/server.go` | 80% done | Extract route handlers |
| `stream.py` | `internal/streaming/` | 0% | Major rewrite needed |
| `detector.py` | `internal/detector/pipeline.go` | 50% | Partial bridge exists |
| `video_processor.py` | `internal/video/` | 0% | **BROKEN - needs full impl** |
| `models.py` | `internal/models/` | 80% done | Just needs review |
| `face_manager.py` | Client calls | N/A | Keep in Python |
| `ocr_engine.py` | Client calls | N/A | Keep in Python |
| `notifier.py` | `internal/api/whatsapp.go` | 60% done | Needs review |
| `polygon.py` | `pkg/utils/polygon.go` | Done | Clean port |
| `database.py` | `internal/models/database.go` | Done | GORM setup |

---

## Phase 3: Detailed Migration Tasks

### 3.1 Fix Video Processing (Priority: CRITICAL)

**Current Problem:**
```go
// video.go line 277-278 - THIS IS THE BUG
time.Sleep(2 * time.Second)  // STUBBED!
job.Status = "done"
```

**Solution:**
1. Use `github.com/AlexandraStranding/gocv` or FFmpeg bindings for video decoding
2. Or: Keep calling Python inference service but fix the path issues
3. Or: Use pure Go video processing with `github.com/blackjack/webm`

**Recommended Approach:** Use FFmpeg via `os/exec` for frame extraction, then call Python inference service per-frame.

```go
// Pseudocode
func processVideoJob(jobID int, videoPath string) {
    // 1. Extract frames using FFmpeg
    frames := extractFrames(videoPath, interval)

    // 2. For each frame, call Python inference
    for i, frame := range frames {
        result := callInferenceService(frame)

        // 3. Draw bounding boxes on frame
        annotated := drawDetections(frame, result)

        // 4. Write to output video
        writeFrame(outputVideo, annotated)

        // 5. Update progress
        updateProgress(jobID, i, total)
    }
}
```

### 3.2 Complete Streaming Server (Priority: HIGH)

**Missing features:**
- MJPEG stream generation with detection overlay
- WebSocket for real-time alerts
- Browser camera WebSocket handler

**Implementation:**
```go
// internal/streaming/stream_manager.go
type StreamManager struct {
    camera    *camera.Camera
    detector  *detector.Pipeline
    violations *violation.Checker
    wsHub     *streaming.Hub
}

// Runs in goroutine, captures frames, runs detection, broadcasts
```

### 3.3 Extract Route Handlers from main.py (Priority: MEDIUM)

Current `main.py` has 946 lines mixing:
- FastAPI app setup
- All route handlers
- WebSocket handlers
- Background tasks
- File uploads

**Plan:** Create modular handler files:
```
internal/api/
  server.go          # Main setup, route registration
  handlers/
    analyze.go       # /analyze/image, /analyze/upload
    polygons.go      # /polygons CRUD
    alerts.go        # /alerts CRUD
    settings.go      # /settings
    stats.go         # /stats, /analytics/compliance
    faces.go         # /faces CRUD
    shutdown.go      # /shutdown/trigger
```

### 3.4 Detection Pipeline (Priority: HIGH)

Current: Go calls Python inference service
Target: Go orchestrates, Python does YOLO

```go
// internal/detector/pipeline.go
type Pipeline struct {
    // Calls Python at localhost:8001 for actual YOLO inference
    // Go handles:
    // - Frame capture
    // - Calling inference service
    // - Merging results
    // - Violation checking
    // - Coordinate transformation
}
```

### 3.5 Face & OCR Integration (Priority: MEDIUM)

Keep in Python inference service, Go calls these endpoints:
- `POST /ocr` - Text recognition
- Face recognition stays in `face_manager.py`

---

## Phase 4: Database Schema Alignment

Check Python `models.py` vs Go `internal/models/`

| Python Model | Go Model | Status |
|-------------|----------|--------|
| Zone | Zone | ✓ |
| Alert | Alert | ✓ |
| Setting | Setting | ✓ |
| VideoJob | VideoJob | Different! Python has more fields |
| ShutdownLog | ShutdownLog | ✓ |
| DetectionLog | DetectionLog | ✓ |
| ZoneOccupancy | - | Not in Go |

**Action:** Review and sync all models.

---

## Phase 5: Testing Strategy

### Unit Tests
```bash
# Test each Go module
go test ./internal/api/...
go test ./internal/detector/...
go test ./internal/video/...
```

### Integration Tests
1. Start Go backend
2. Start Python inference service
3. Test each endpoint with curl
4. Test video upload and processing
5. Test WebSocket connections

### Load Tests
- Stream 30 FPS for 10 minutes
- Process 10-minute video
- Concurrent alert handling

---

## Phase 6: Deployment

### Current
```bash
# Python backend
cd backend && venv\Scripts\activate && python main.py

# Python inference
cd inference-service && python main.py

# Go backend (optional)
./siews-backend.exe
```

### Target (Docker Compose)
```yaml
services:
  api:
    build: ./backend-go
    ports:
      - "8080:8080"
    depends_on:
      - inference
    environment:
      - INFERENCE_URL=http://inference:8001

  inference:
    build: ./inference-service
    ports:
      - "8001:8001"
    volumes:
      - ./model:/app/model

  # Optional: Redis for caching, etc.
```

---

## Implementation Order

```
Week 1: Fix Critical Bugs
├── Fix video processing (0 frames → actually processes)
├── Fix safety-cone false positives
└── Verify current Go backend works

Week 2: Complete Go API
├── Extract route handlers from main.py
├── Complete video upload/processing in Go
├── Complete MJPEG streaming
└── WebSocket alerts

Week 3: Polish
├── Face/OCR integration
├── Notification system review
├── Testing
└── Documentation

Week 4: Deployment
├── Docker setup
├── CI/CD pipeline
└── Production deployment
```

---

## Key Files Reference

### Go Backend Structure
```
backend-go/
├── cmd/server/main.go           # Entry point
├── internal/
│   ├── api/
│   │   ├── server.go           # Gin setup, routes
│   │   ├── video.go           # Video processing (NEEDS FIX)
│   │   ├── faces.go
│   │   ├── whatsapp.go
│   │   └── shutdown.go
│   ├── camera/
│   │   └── camera.go           # Camera capture
│   ├── detector/
│   │   ├── pipeline.go         # Detection orchestration
│   │   ├── bridge.go           # Calls Python inference
│   │   └── onnx_loader.go
│   ├── models/
│   │   └── database.go         # GORM models
│   └── streaming/
│       └── hub.go              # WebSocket hub
└── pkg/utils/
    └── polygon.go              # Point-in-polygon
```

### Python Inference Service (Keep as-is for now)
```
inference-service/
├── main.py                     # FastAPI server (port 8001)
├── detector.py                 # YOLO wrapper
└── (models are loaded from ../backend/model/New/)
```

---

## Success Criteria

1. ✓ Video upload processes frames and generates annotated output
2. ✓ MJPEG stream shows live detection overlay
3. ✓ All API endpoints return correct responses
4. ✓ WebSocket alerts fire correctly
5. ✓ Face/OCR integration works
6. ✓ Single `docker-compose up` deploys everything
7. ✓ Zero Python backend dependencies for production

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Video processing complex | High | Use FFmpeg wrapper, not pure Go |
| Face recognition accuracy | Medium | Keep Python implementation |
| Real-time performance | Medium | Profile and optimize frame handling |
| Model loading in Python | Low | Keep inference in Python service |

---

## Questions to Resolve

1. Should we keep Python inference service long-term, or port YOLO to Go (via ONNX Runtime)?
2. Video processing - use FFmpeg or pure Go library?
3. Face recognition - keep in Python or use Go face library?
4. Database - keep SQLite or migrate to PostgreSQL?
