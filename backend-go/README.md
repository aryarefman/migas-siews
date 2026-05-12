# SIEWS+ 5.0 Go Backend

A high-performance Go backend for the SIEWS+ (Smart Industrial Electronic Worker Safety System) built with Gin, WebSocket, and GORM.

## Features

- **REST API** - Full CRUD for zones, alerts, settings, and video jobs
- **WebSocket** - Real-time streaming and alert notifications
- **Multi-Stage Detection** - Integration with Python inference service for:
  - Person detection (Stage 1)
  - PPE Detection (Stage 2)
  - Environment/Hazard Detection (Stage 3)
  - Road Damage Detection (Stage 5)
- **Polygon Zones** - Zone management with risk levels
- **WhatsApp Notifications** - Fonnte API integration for alerts
- **Shutdown Relay** - GPIO/Network control for safety systems
- **Video Processing** - Async video analysis jobs
- **Database** - SQLite (default) or PostgreSQL support

## Project Structure

```
backend-go/
├── cmd/
│   └── server/
│       └── main.go              # Application entry point
├── internal/
│   ├── api/
│   │   ├── server.go            # Gin HTTP server
│   │   ├── shutdown.go          # Shutdown relay handler
│   │   └── whatsapp.go          # Fonnte WhatsApp client
│   ├── camera/
│   │   └── camera.go            # Camera capture with gocv
│   ├── detector/
│   │   ├── bridge.go            # Python inference service client
│   │   ├── onnx_loader.go       # Model configuration
│   │   └── pipeline.go          # Multi-stage detection pipeline
│   └── models/
│       └── database.go          # GORM models
├── pkg/
│   └── utils/
│       └── polygon.go           # Polygon utilities
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # Service orchestration
└── go.mod                       # Go modules
```

## Quick Start

### Prerequisites

- Go 1.23+
- (Optional) Docker & Docker Compose

### Local Development

1. Install dependencies:
```bash
cd backend-go
go mod download
```

2. Run the server:
```bash
go run ./cmd/server
```

### Docker

Build and run:
```bash
docker build -t siews-backend .
docker run -p 8000:8000 siews-backend
```

Or use Docker Compose:
```bash
docker-compose up --build
```

## API Endpoints

### Health
- `GET /health` - Health check

### Analysis
- `POST /api/analyze/image` - Analyze base64 image
- `POST /api/analyze/upload` - Upload and analyze image

### Zones
- `GET /api/polygons` - List all zones
- `POST /api/polygons` - Create zone
- `PUT /api/polygons/:id` - Update zone
- `DELETE /api/polygons/:id` - Delete zone

### Alerts
- `GET /api/alerts` - List alerts (paginated)
- `POST /api/alerts/:id/resolve` - Mark as resolved
- `POST /api/alerts/:id/false-positive` - Mark as false positive
- `GET /api/alerts/:id/detections` - Get detection logs

### Shutdown
- `POST /api/shutdown/trigger` - Trigger shutdown relay

### Settings
- `GET /api/settings` - Get all settings
- `POST /api/settings` - Update setting
- `POST /api/settings/notify-test` - Send test notification

### Stats
- `GET /api/stats` - Dashboard stats
- `GET /api/analytics/compliance` - Compliance analytics

### Video
- `POST /api/video/upload` - Upload video for processing
- `GET /api/video/jobs` - List processing jobs
- `GET /api/video/jobs/:id` - Get job status
- `GET /api/video/jobs/:id/result` - Get job results
- `DELETE /api/video/jobs/:id` - Delete job

### WebSocket
- `WS /ws/stream` - MJPEG video stream with detection overlay
- `WS /ws/alerts` - Real-time alert notifications

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| PORT | 8000 | Server port |
| DATABASE_URL | sqlite:///siews.db | Database connection string |
| INFERENCE_URL | http://localhost:8001 | Python inference service URL |
| STATIC_DIR | ./static | Static file directory |
| MODELS_DIR | ../../backend/models | YOLO model directory |
| FONNTE_TOKEN | - | WhatsApp Fonnte API token |
| DEFAULT_RECIPIENTS | - | Comma-separated phone numbers |
| FACILITY_NAME | Offshore Platform A | Facility name for alerts |

## Database Schema

### Zone
- id, name, vertices_json, color, active, risk_level, zone_type, dwell_threshold, created_at

### Alert
- id, zone_id, confidence, snapshot_path, timestamp, shutdown_triggered, resolved, violation_type, false_positive, ppe_detail, persons_count

### DetectionLog
- id, alert_id, class_name, confidence, crop_path, frame_number, bbox_json, is_false_positive, created_at

### ShutdownLog
- id, zone_id, trigger_source, triggered_at

### Setting
- id, key, value

### VideoJob
- id, filename, file_path, status, progress, total_frames, processed_frames, result_json, error_message, created_at, completed_at

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Browser   │────▶│  Go Backend  │────▶│ Python Inference│
│  (React)   │◀────│    (Gin)    │◀────│    Service      │
└─────────────┘     └──────────────┘     └─────────────────┘
      │                   │                      │
      │                   ▼                      ▼
      │            ┌──────────────┐     ┌─────────────┐
      │            │   SQLite/     │     │  YOLO .pt    │
      │            │  PostgreSQL   │     │   Models     │
      │            └──────────────┘     └─────────────┘
      │
      ▼
┌─────────────┐
│  WebSocket  │
│   Stream    │
└─────────────┘
```

## License

Apache-2.0
