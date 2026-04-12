# SIEWS+ 5.0 — Smart Integrated Early Warning System Plus

> AI-Based Human Presence Detection for Intelligent Safety Shutdown
> Designed for upstream oil & gas facilities (offshore platforms, onshore processing areas)

![Status](https://img.shields.io/badge/version-5.0-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Node](https://img.shields.io/badge/node-18%2B-green)

---

## 🏗️ Overview

SIEWS+ 5.0 is an AI-powered safety monitoring system that:

- 📷 **Streams live camera footage** from hazardous zones via MJPEG
- 🧠 **Detects human presence** using YOLOv8 computer vision
- 🗺️ **Checks zone violations** via polygon-based restricted areas
- 🚨 **Triggers intelligent shutdown signals** when high-risk zones are breached
- 💬 **Sends real-time WhatsApp alerts** to supervisors via Fonnte API
- 📊 **Logs all incidents** for safety reporting and compliance

### Core Flow

```
IP Camera → Backend (YOLOv8) → Zone Check (polygon) → Alert + Shutdown → WhatsApp → Dashboard
```

---

## 🛠️ Tech Stack

| Layer      | Technology                                      |
|------------|------------------------------------------------|
| Frontend   | Next.js 14 (App Router) + Tailwind CSS          |
| Backend    | Python FastAPI                                   |
| Detection  | YOLOv8n (ultralytics)                           |
| Streaming  | OpenCV → MJPEG via FastAPI                       |
| Realtime   | FastAPI WebSocket                                |
| Notif      | Fonnte API (WhatsApp)                            |
| Database   | SQLite + SQLAlchemy                              |
| Serving    | Uvicorn (backend) + Next.js dev server (frontend)|

---

## 📋 Prerequisites

- **Python** 3.10+
- **Node.js** 18+
- **A webcam** (for demo) or **IP camera** with RTSP support
- **Fonnte API token** (optional, for WhatsApp notifications — register at [fonnte.com](https://fonnte.com))

---

## 🚀 Quick Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install fastapi uvicorn opencv-python ultralytics sqlalchemy aiofiles python-dotenv httpx

# Configure environment
# Edit .env file with your settings (camera source, Fonnte token, etc.)

# Start backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### 3. Access the Application

- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

---

## 📷 Camera Configuration

### Demo Mode (Webcam)

Set in `backend/.env`:
```
CAMERA_SOURCE=0
```

### IP Camera (RTSP)

```
CAMERA_SOURCE=rtsp://username:password@192.168.1.100:554/stream
```

Common RTSP URL formats:
- Hikvision: `rtsp://admin:password@IP:554/Streaming/Channels/101`
- Dahua: `rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=0`
- Generic: `rtsp://IP:554/stream`

---

## 💬 WhatsApp Notification (Fonnte)

1. Register at [fonnte.com](https://fonnte.com)
2. Link your WhatsApp number
3. Get your API token
4. Set `FONNTE_TOKEN` in backend `.env` or via Settings page
5. Add recipient phone numbers (format: `628xxxxxxxxx`)

---

## 📁 Project Structure

```
migas-siews/
├── backend/
│   ├── main.py          # FastAPI entry point, CORS, all endpoints
│   ├── stream.py        # MJPEG stream + YOLO detection pipeline
│   ├── detector.py      # YOLOv8 wrapper
│   ├── polygon.py       # Ray-casting point-in-polygon
│   ├── notifier.py      # WhatsApp via Fonnte API
│   ├── shutdown.py      # Shutdown signal handler
│   ├── models.py        # SQLAlchemy ORM models
│   ├── database.py      # DB engine + session
│   ├── config.py        # Environment variables
│   ├── requirements.txt # Python dependencies
│   ├── .env             # Environment config
│   └── static/
│       └── snapshots/   # Violation screenshots
├── frontend/
│   ├── app/
│   │   ├── layout.tsx       # Root layout + Navbar
│   │   ├── page.tsx         # Redirect to /dashboard
│   │   ├── dashboard/       # Main monitoring page
│   │   ├── incidents/       # Incident log + filters
│   │   ├── zones/           # Zone management
│   │   └── settings/        # System configuration
│   ├── components/
│   │   ├── Navbar.tsx       # Top navigation
│   │   ├── VideoCanvas.tsx  # MJPEG + polygon overlay
│   │   ├── ZoneEditor.tsx   # Zone list panel
│   │   ├── AlertFeed.tsx    # Live alert sidebar
│   │   ├── AlertCard.tsx    # Single alert card
│   │   └── ShutdownBanner.tsx # Shutdown warning banner
│   ├── .env.local           # Frontend env vars
│   └── package.json
└── README.md
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/stream` | MJPEG video stream |
| GET    | `/polygons` | List restricted zones |
| POST   | `/polygons` | Create new zone |
| PUT    | `/polygons/{id}` | Update zone |
| DELETE | `/polygons/{id}` | Delete zone |
| GET    | `/alerts` | Paginated incident log |
| POST   | `/alerts/{id}/resolve` | Mark incident resolved |
| POST   | `/shutdown/trigger` | Manual shutdown signal |
| GET    | `/settings` | Get all settings |
| POST   | `/settings` | Update a setting |
| POST   | `/settings/notify-test` | Test WhatsApp |
| WS     | `/ws/alerts` | Real-time alert push |
| GET    | `/stats` | Dashboard statistics |

---

## ⚙️ Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `CAMERA_SOURCE` | `0` | Webcam index or RTSP URL |
| `FACILITY_NAME` | `Offshore Platform A` | Facility name for alerts |
| `CONFIDENCE_THRESHOLD` | `0.5` | YOLO detection threshold |
| `DETECTION_INTERVAL` | `3` | Run inference every N frames |
| `NOTIFY_COOLDOWN` | `300` | Min seconds between alerts per zone |
| `FONNTE_TOKEN` | `""` | Fonnte WhatsApp API token |
| `DEFAULT_RECIPIENTS` | `""` | Comma-separated phone numbers |

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API URL |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Backend WebSocket URL |

---

## 🏭 Restricted Zone Examples

For upstream oil & gas facilities:
- **Wellhead Area** — High Risk
- **High-Pressure Manifold Zone** — High Risk
- **Rotating Equipment Zone** (pumps, compressors) — High Risk
- **Chemical Injection Area** — Low Risk
- **ESDV (Emergency Shutdown Valve) Perimeter** — High Risk

---

## 📜 License

This project was built for the IOC Digital Hackathon AI/ML Data Analytics Hulu Migas 2026.
