# SentinelAI — Autonomous Public Safety Incident Intelligence

> **Hackathon Pitch Demo & Security Operations Center (SOC) Control Room**  
> AI-powered public safety monitoring turning authorized CCTV video feeds into verified, evidence-backed incident alerts for human operators.

---

## Key Guarantees & Compliance Rules
- **No Facial Recognition or Biometric Identification**: Strict anonymous person tracking and skeleton keypoint topology only.
- **Human-in-the-Loop**: Operators acknowledge and resolve alerts; the system never executes autonomous physical actions.
- **100% Offline Capability**: Runs entirely on a single laptop without internet access, external cloud APIs, or mandatory GPU hardware.
- **Zero-Failure Demo Safety Layer**: Survives backend restarts, network drops, missing video files, and detector exceptions without UI blank screens.

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │    Authorized CCTV Feeds (15 FPS)      │
                      └──────────────────┬─────────────────────┘
                                         │
                                         ▼
                 ┌──────────────────────────────────────────────────┐
                 │       SentinelAI Computer Vision Pipeline        │
                 │   - YOLOv8 Pose / Classical Contour Tracker      │
                 │   - Farneback Dense Optical Flow                 │
                 │   - Sliding Window Temporal Verification (2.5s)   │
                 └───────┬──────────────────────────────────┬───────┘
                         │                                  │
      MJPEG Video Stream │ (Annotations & Overlays)         │ Verified Incidents (HTTP POST)
                         ▼                                  ▼
┌────────────────────────────────────────┐         ┌────────────────────────────────────────┐
│           FrameHub (In-Memory)         │         │         FastAPI Backend (:8000)        │
│   - Latest JPEG Buffers                │         │   - REST API & SQLite (WAL mode)       │
│   - Standby Fail-Safe Placeholders     │         │   - WebSocket Broadcaster (/ws/incidents│
└──────────────────┬─────────────────────┘         └──────────────────┬─────────────────────┘
                   │                                                  │
                   │ /api/stream/{cam_id}                             │ /ws/incidents & /api/*
                   └─────────────────────┬────────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────────┐
                 │      React 18 + Vite Control-Room Dashboard      │
                 │   - Live Ops 2x2 Camera Matrix & Event Feed      │
                 │   - Leaflet Dark Matter Geospatial Radar Map     │
                 │   - Incident Drawer with Clip Player & Audit     │
                 │   - Auto-reconnect & Autonomous Mock Fallback    │
                 └──────────────────────────────────────────────────┘
```

---

## Incident Detections Supported

1. **Fall & Collapse (`fall_collapse`)**:
   - Detects sudden downward vertical displacement of hip and head keypoints, followed by horizontal torso orientation and stillness sustained across $\ge 15$ frames over a 2.5-second temporal window.
2. **Physical Altercation (`physical_altercation`)**:
   - Evaluates track pairs in close interpersonal proximity with sustained high-velocity wrist/arm oscillation or violent approach/retreat dynamics across $\ge 18$ frames.
3. **Abnormal Crowd Movement (`abnormal_crowd_movement`)**:
   - Identifies rapid optical flow velocity spikes exceeding $2.2\times$ rolling median baseline paired with high directional divergence across pedestrian tracks.

---

## Quickstart: Clean Environment Installation & Run

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**

### 2. Backend Setup & Run
Open a terminal in the project root:

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS / Linux:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 2b. (Online step) Pre-download YOLOv8-Pose weights before going offline:
# Pre-trained weights (yolov8n-pose.pt) are excluded from the repository deliverable.
# Run this once while connected to the internet to cache the model locally:
python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"

# 3. Setup Video Assets (Two Options):
# Option A (Offline quickstart): Generate synthetic surveillance clips
python data/sample_generator.py

# Option B (Recommended for full YOLOv8-Pose AI evaluation):
# Review data/videos/SOURCES.md to acquire real CCTV research footage into data/videos/
# (Note: cam_04_normal.mp4 is already bundled under Apache 2.0 license)

# 4. Start the FastAPI backend server
python backend/run.py
```
*Backend runs on `http://localhost:8000`.*

---

## Model Weights & Offline Inference Architecture

### 1. Model Weight Packaging & Distribution
The deliverable ZIP does **not** bundle `yolov8n-pose.pt`. Pre-trained neural network weights are released under Ultralytics licensing terms and must be downloaded directly by the user from upstream releases.

### 2. Preparing for 100% Offline Field Operation
To operate SentinelAI in an offline SOC or hackathon presentation without internet access:
1. While connected to the internet, run:
   ```bash
   python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"
   ```
2. Verify that `yolov8n-pose.pt` (~6.5 MB) is present in the project root.
3. The system is now 100% offline-ready: all future launches will load the local weights file with zero network calls.

### 3. What Happens If the Model Is Unavailable (Classical Fallback)
If SentinelAI is launched offline on a fresh machine without `yolov8n-pose.pt`:
* `VisionTracker` catches the missing file / network failure gracefully and activates the **Classical Computer Vision Pose Tracker fallback** (`use_fallback = True`).
* The fallback uses OpenCV MOG2 background subtraction, morphological noise filtering, and contour bounding-box geometry.
* **Important Limitation**: The classical fallback preserves uninterrupted MJPEG streaming and person bounding boxes, but it **does not provide equivalent neural pose detection** (no 17-point COCO skeleton keypoints, joint angles, or wrist velocities). Genuine neural pose detection for `fall_collapse` and `physical_altercation` requires the local `yolov8n-pose.pt` weights.

---

## Video Assets & Legal Licensing

### Redistribution Permissions vs Academic Research Use
* **Bundled in Deliverable**: `data/videos/cam_04_normal.mp4` (20.0s pedestrian negative control) is formally licensed under the **Apache License 2.0** and is included in the ZIP.
* **Excluded from Deliverable**: Research clips for `cam_01_fall.mp4`, `cam_02_altercation.mp4`, and `cam_03_crowd.mp4` are **strictly excluded** from redistribution ZIP archives because their academic terms permit individual research/educational evaluation but do *not* grant open redistribution or sublicensing rights.
* **Acquisition**: Complete URLs and PowerShell/curl extraction commands for research clips are documented in [`data/videos/SOURCES.md`](data/videos/SOURCES.md).
* **Synthetic Clip Limitations**: `python data/sample_generator.py` generates 4 synthetic clips offline for testing server streaming, UI tiles, and optical flow crowd surge. However, because YOLOv8-Pose is trained on photographic humans, evaluating full neural pose detection on fall and altercation requires real human CCTV footage as documented in `SOURCES.md`. Live drills can also be demonstrated at any time using `/api/simulate` or dashboard Demo Mode.

### 3. Frontend Setup & Run
Open a second terminal in the project root:

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
*Frontend runs on `http://localhost:5173`.*

---

## Standalone Computer Vision Runner & Tuning

You can run the vision pipeline with a live OpenCV debug window:

```bash
# Run standalone preview on camera 1
python -m sentinel_ai.run --camera cam_01 --show
```

To tune detection sensitivity, refer to [`sentinel_ai/TUNING_GUIDE.md`](sentinel_ai/TUNING_GUIDE.md) and adjust parameters in [`sentinel_ai/config.yaml`](sentinel_ai/config.yaml).

---

## Automated Tests

Run the full automated test suite (AI detectors and Backend REST APIs):

```bash
# Run detector unit tests
python -m pytest sentinel_ai/tests

# Run backend REST and streaming API tests
python -m pytest backend/tests

# Run full end-to-end integration test
python test_e2e.py
```

---

## Shared Contract Specification

### Incident Object
```json
{
  "id": "inc_0001",
  "camera_id": "cam_01",
  "camera_name": "Central Plaza - North",
  "location": { "lat": 12.9716, "lng": 77.5946, "label": "Central Plaza" },
  "type": "physical_altercation",
  "confidence": 0.89,
  "severity": "high",
  "timestamp": "2026-10-09T18:00:00Z",
  "status": "new",
  "snapshot_url": "/media/snapshots/inc_0001.jpg",
  "clip_url": "/media/clips/inc_0001.mp4",
  "notes": "Verified anomalous activity.",
  "verification": {
    "window_seconds": 2.5,
    "frames_confirmed": 38,
    "frames_required": 30
  }
}
```

### Endpoints
- `GET    /api/health` — System status and online camera count.
- `GET    /api/cameras` — List authorized feeds.
- `GET    /api/incidents?status=&type=&camera_id=` — Filterable incident log.
- `GET    /api/incidents/{id}` — Single incident record.
- `PATCH  /api/incidents/{id}` — Update status (`acknowledged`, `resolved`) or operator notes.
- `GET    /api/stats` — Incident counts by type, status, hour, and camera.
- `POST   /api/simulate` — Trigger deterministic incident drill for live demos.
- `POST   /api/internal/incidents` — CV pipeline event ingress; requires `X-Internal-Token` matching the backend `INTERNAL_INGEST_TOKEN` environment setting.
- `GET    /api/stream/{camera_id}` — MJPEG live stream with bounding boxes and pose overlay.
- `GET    /media/...` — Static snapshot JPEGs and MP4 clips.
- `WS     /ws/incidents` — Broadcasts `{ "event": "incident.created" | "incident.updated", "data": <Incident> }`.

---

## Demo Safety & Pitch Reliability
- **Backend Restart**: All records persist in SQLite (`sentinel.db`). On restart, the frontend automatically reconnects and reloads state.
- **Frontend Restart**: Hydrates telemetry instantly from `GET /api/incidents` and `GET /api/stats`.
- **Offline / Mock Mode**: Toggle `VITE_USE_MOCK=true` or click the **Demo Mode** button in the dashboard to generate deterministic incidents without requiring any external dependencies.
