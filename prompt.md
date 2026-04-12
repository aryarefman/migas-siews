Build a complete web application called "SIEWS+ 5.0" (AI-Based Human Presence Detection for Intelligent Safety Shutdown). This system is designed for upstream oil & gas facilities. It streams live camera footage from hazardous zones, detects human presence using computer vision, triggers intelligent safety shutdown signals, and sends real-time alerts to operators via WhatsApp. The goal is to prevent workplace accidents caused by unauthorized human entry into dangerous machinery or restricted areas in offshore/onshore oil & gas facilities.

═══════════════════════════════════════════
1. PROJECT OVERVIEW
═══════════════════════════════════════════

Name        : SIEWS+ 5.0 (Smart Integrated Early Warning System Plus)
Context     : Upstream oil & gas facility — offshore platform or onshore processing area
Problem     : Workers entering hazardous zones near active machinery without authorization can cause fatal accidents and production shutdowns
Solution    : AI-powered camera monitoring that automatically detects human presence in defined restricted zones, triggers audio/visual alerts, sends WhatsApp notifications to supervisors, and logs all incidents for safety reporting

Core flow   : IP Camera → Backend (YOLOv8 person detection) → Zone boundary check (polygon) → Alert + Shutdown signal → WhatsApp notification → Dashboard log

Restricted zone examples (for context, not hardcoded):
  - Wellhead area
  - High-pressure manifold zone
  - Rotating equipment zone (pumps, compressors)
  - Chemical injection area
  - Emergency shutdown valve (ESDV) perimeter

═══════════════════════════════════════════
2. TECH STACK
═══════════════════════════════════════════

Frontend  : Next.js 14 (App Router) + Tailwind CSS + HTML5 Canvas API
Backend   : Python FastAPI
Streaming : OpenCV VideoCapture → MJPEG stream via FastAPI
Detection : YOLOv8n (ultralytics) — inference every 3rd frame, filter class "person"
Realtime  : FastAPI WebSocket — push alert events to frontend instantly
Notif     : Fonnte API (fonnte.com) for WhatsApp — HTTP POST, supports Indonesian numbers
Database  : SQLite via SQLAlchemy
Serving   : Uvicorn (backend), Next.js dev server or `next start` (frontend)

═══════════════════════════════════════════
3. BACKEND — Python FastAPI
═══════════════════════════════════════════

File structure:
  backend/
    main.py        ← FastAPI app entry, CORS, router mounting, static files
    stream.py      ← MJPEG stream loop + YOLO inference + zone violation check
    detector.py    ← YOLOv8 wrapper: load model, run inference, return bbox list
    polygon.py     ← Polygon CRUD + ray-casting point-in-polygon algorithm
    notifier.py    ← WhatsApp alert via Fonnte API
    shutdown.py    ← Shutdown signal handler (log signal, simulate relay trigger)
    models.py      ← SQLAlchemy ORM models
    database.py    ← DB engine + session setup
    config.py      ← Load all .env variables

API endpoints:
  GET  /stream                        → MJPEG video stream
  GET  /polygons                      → List all saved restricted zones
  POST /polygons                      → Create zone {name, vertices, color, active, risk_level}
  PUT  /polygons/{id}                 → Update zone
  DELETE /polygons/{id}               → Delete zone
  GET  /alerts?page=1&limit=20        → Paginated incident log
  POST /alerts/{id}/resolve           → Mark incident as resolved
  POST /shutdown/trigger              → Manually trigger shutdown signal for a zone
  POST /settings/notify-test          → Send test WhatsApp to all recipients
  GET  /settings                      → Get all settings
  POST /settings                      → Update a setting key-value
  WebSocket /ws/alerts                → Push real-time alert events to frontend

Detection & alert pipeline (stream.py):
  1. Open camera: cv2.VideoCapture(CAMERA_SOURCE)
     CAMERA_SOURCE = 0 (webcam) or RTSP URL from .env (e.g., rtsp://192.168.1.100/stream)
  2. Every DETECTION_INTERVAL frames (default 3), run YOLO inference
  3. Filter results: class "person" (COCO index 0), confidence >= CONFIDENCE_THRESHOLD (default 0.5)
  4. For each detected person, compute bottom-center point: ((x1+x2)/2, y2), normalized 0–1
  5. Check if point is inside any active restricted zone polygon (ray-casting)
  6. If violation detected AND per-zone cooldown has expired (default 30 seconds):
     a. Save JPEG snapshot to /static/snapshots/{timestamp}.jpg
     b. Insert alert to DB: zone_id, timestamp, confidence, snapshot_path, shutdown_triggered, resolved=False
     c. Call notifier.py → send WhatsApp to all active recipients
     d. Call shutdown.py → log shutdown signal (and optionally trigger GPIO/relay output)
     e. Broadcast WebSocket event:
        { type: "alert", zone_name, risk_level, timestamp, confidence, snapshot_url, shutdown_triggered }
     f. Reset cooldown for that zone
  7. Draw all active zone polygons on frame:
     - Low risk  → yellow fill (25% opacity) + yellow border
     - High risk → red fill (25% opacity) + red border
     - Zone name label at centroid
  8. Draw bounding boxes:
     - Person detected, NOT in zone → green box
     - Person detected, IN zone → red box + "BAHAYA" label above box
  9. Yield JPEG frame as MJPEG chunk

Shutdown signal (shutdown.py):
  - For hackathon/demo: log the shutdown event to DB with timestamp, zone_name, trigger_source ("auto" or "manual")
  - Add a placeholder function trigger_relay() that prints "SHUTDOWN SIGNAL SENT TO ZONE: {zone_name}" — this is where real GPIO/PLC integration would be wired in production
  - Expose POST /shutdown/trigger endpoint for manual override from dashboard

Polygon data (polygon.py):
  - vertices stored as JSON: list of [x, y] normalized floats (0.0–1.0)
  - Each polygon has a risk_level field: "low" or "high"
  - "high" risk zones trigger both notification AND shutdown signal
  - "low" risk zones trigger notification only (warning)
  - Ray-casting algorithm for point-in-polygon

Notification (notifier.py):
  - POST https://api.fonnte.com/send
    Headers: { "Authorization": FONNTE_TOKEN }
    Body: { "target": phone, "message": text, "countryCode": "62" }
  - Message format:
      "🚨 SIEWS+ ALERT — ZONA TERLARANG DILANGGAR
      Fasilitas : {FACILITY_NAME}
      Zona      : {zone_name}
      Risiko    : {risk_level.upper()}
      Waktu     : {timestamp WIB}
      Confidence: {confidence:.0f}%
      Shutdown  : {'AKTIF' if shutdown_triggered else 'TIDAK'}
      
      Segera periksa area dan ambil tindakan."
  - Send to all active recipients in settings table
  - Per-zone cooldown: max 1 message per zone per NOTIFY_COOLDOWN seconds (default 300)

Database models (models.py):
  Table zones (previously "polygons"):
    id, name, vertices_json (TEXT), color (hex), active (bool),
    risk_level (str: "low" or "high"), created_at

  Table alerts:
    id, zone_id (FK → zones.id), confidence (float), snapshot_path (str),
    timestamp (datetime UTC), shutdown_triggered (bool), resolved (bool default False)

  Table shutdown_log:
    id, zone_id (FK), trigger_source (str: "auto" or "manual"), triggered_at (datetime)

  Table settings:
    id, key (unique), value
    Default seed rows:
      camera_source        = "0"
      facility_name        = "Offshore Platform A"
      confidence_threshold = "0.5"
      detection_interval   = "3"
      notify_cooldown      = "300"
      fonnte_token         = ""
      recipients           = ""

═══════════════════════════════════════════
4. FRONTEND — Next.js 14 (App Router)
═══════════════════════════════════════════

File structure:
  frontend/
    app/
      layout.tsx             ← Root layout: top navbar + dark industrial theme
      page.tsx               ← Redirect to /dashboard
      dashboard/page.tsx     ← Main monitoring page
      incidents/page.tsx     ← Incident log + filter + export
      zones/page.tsx         ← Zone management page
      settings/page.tsx      ← System configuration page
    components/
      VideoCanvas.tsx        ← MJPEG stream + polygon drawing + bbox overlay
      ZoneEditor.tsx         ← Zone list panel (add, edit, delete, toggle)
      AlertFeed.tsx          ← Live alert sidebar via WebSocket
      AlertCard.tsx          ← Single alert card component
      ShutdownBanner.tsx     ← Full-width red banner shown when shutdown is active
      Navbar.tsx             ← Top nav with system status indicator

UI Theme:
  - Dark industrial theme appropriate for oil & gas control room aesthetic
  - Primary background: dark gray (#0f1117 or Tailwind slate-900)
  - Accent color: amber/orange for warnings, red for danger, green for safe
  - Font: monospace feel for status displays, sans-serif for readable text
  - All times displayed in WIB (UTC+7)

VideoCanvas.tsx:
  - Display MJPEG stream: <img src={`${API_URL}/stream`} />
  - Overlay <canvas> absolutely on top, same size, pointer-events for drawing
  - All coordinates normalized to 0–1 range
  - Drawing mode:
    * Click = place vertex (show dot)
    * Mouse move = preview line from last vertex to cursor
    * Double-click = close polygon → open dialog (zone name + risk level selector) → POST /zones
  - Zone rendering per risk_level:
    * "low"  → yellow semi-transparent fill + yellow border + zone name label
    * "high" → red semi-transparent fill + red border + zone name label + skull icon (SVG)
  - Edit mode: drag existing vertex → PUT /zones/{id} on mouse-up
  - On WebSocket alert: flash red border on entire canvas for 2 seconds + show BAHAYA overlay text
  - Camera offline detection: show "KAMERA OFFLINE — MENCOBA RECONNECT" overlay, retry every 5s

ZoneEditor.tsx (left panel):
  - List all zones from GET /zones
  - Each row: color indicator, zone name, risk badge (LOW/HIGH), active toggle, edit button, delete button
  - "Tambah Zona Baru" button → activate drawing mode on VideoCanvas
  - Zone count summary at top: "X zona aktif"

AlertFeed.tsx (right sidebar):
  - Connect to WebSocket on mount, reconnect on disconnect
  - On new alert event:
    * Play audio beep (Web Audio API, 440Hz, 300ms) — louder and longer if risk_level = "high"
    * If shutdown_triggered = true: show ShutdownBanner component
    * Prepend AlertCard to feed
  - AlertCard shows: zone name, risk badge, time (relative), confidence %, snapshot thumbnail, resolve button
  - "X Insiden Aktif" badge at top (count of unresolved alerts)
  - Max 30 cards in feed

ShutdownBanner.tsx:
  - Full-width red banner: "⚠ SHUTDOWN OTOMATIS AKTIF — ZONA: {zone_name} — {timestamp}"
  - Pulsing red border animation (CSS)
  - "Konfirmasi & Reset" button → POST /alerts/{id}/resolve + hide banner

Dashboard layout (dashboard/page.tsx):
  - Three columns:
    * Left (20%): ZoneEditor panel
    * Center (55%): VideoCanvas
    * Right (25%): AlertFeed
  - Top: ShutdownBanner (conditionally shown, full width above columns)
  - Status bar below navbar: Facility name | Camera status | Active zones count | Today's incident count

Incidents page (incidents/page.tsx):
  - Table: No, Zona, Waktu, Risk Level, Confidence, Shutdown, Status, Aksi
  - Filters: date range picker, zone dropdown, risk level, status
  - "Export CSV" button (client-side from fetched data)
  - Resolve button per row

Zones page (zones/page.tsx):
  - Alternative zone management view (card grid instead of table)
  - Each card: zone name, risk level badge, active status, vertex count, last violation timestamp
  - Quick toggle active/inactive without going to dashboard

Settings page (settings/page.tsx):
  - Camera source input (0 or RTSP URL)
  - Facility name input
  - Confidence threshold slider (0.3–0.9, step 0.05)
  - Detection interval input (1–10)
  - Notify cooldown input (minutes)
  - Fonnte token input (password field, show/hide toggle)
  - Recipients list: add/remove phone numbers (format 628xxxxxxx), name label per recipient
  - "Test Kirim WhatsApp" button → POST /settings/notify-test → toast result
  - "Simpan" button

═══════════════════════════════════════════
5. SETUP & ENVIRONMENT
═══════════════════════════════════════════

backend/.env:
  CAMERA_SOURCE=0
  FACILITY_NAME=Offshore Platform A
  CONFIDENCE_THRESHOLD=0.5
  DETECTION_INTERVAL=3
  NOTIFY_COOLDOWN=300
  FONNTE_TOKEN=your_token_here
  DEFAULT_RECIPIENTS=628xxxxxxx

frontend/.env.local:
  NEXT_PUBLIC_API_URL=http://localhost:8000
  NEXT_PUBLIC_WS_URL=ws://localhost:8000

README.md must include:
  - Prerequisites: Python 3.10+, Node.js 18+
  - Backend:
      pip install fastapi uvicorn opencv-python ultralytics sqlalchemy aiofiles python-dotenv
      uvicorn main:app --host 0.0.0.0 --port 8000 --reload
  - Frontend:
      npm install
      npm run dev
  - Notes on RTSP camera setup and Fonnte API token registration
  - Demo mode: use webcam (CAMERA_SOURCE=0) if no IP camera available

Additional requirements:
  - CORS: allow http://localhost:3000
  - Timestamps: store UTC, display WIB (UTC+7) on frontend
  - Snapshots: saved to backend/static/snapshots/, served as FastAPI static files
  - Graceful camera reconnect: if stream drops, frontend retries every 5 seconds
  - Mobile-responsive: on small screens stack canvas and alert feed vertically

Build order: backend stream + detection first → confirm /stream works → polygon CRUD → WebSocket → frontend VideoCanvas → AlertFeed → ShutdownBanner → notifications → Settings page.