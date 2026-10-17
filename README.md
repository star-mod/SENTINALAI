# SentinelAI

**AI-assisted incident detection and response for authorized, prerecorded CCTV footage.**

SentinelAI watches video feeds, flags candidate safety incidents (a person falling, a physical altercation, abnormal crowd movement), saves annotated evidence, and shows everything on a live operator dashboard where a human reviews, acknowledges and resolves each alert. It never identifies people and never acts on its own.

> **Live demo:** `https://YOUR-DASHBOARD.onrender.com`  <https://sentinalai-1-m5nl.onrender.com>
> The demo backend may sleep when idle (first load can take up to ~1 minute). AI detection runs on a team machine during judging; see [Status](#status-and-limitations).

---

## What it does

```
Video feed ─► AI pipeline ─► FastAPI backend ─► Database ─► React dashboard
 (YOLO pose      (temporal       (validates,       (SQLite)    (live via WebSocket)
  + tracking)     detectors)      stores, queues)       │
                                                        └──► n8n ─► Telegram   (planned, see Status)
```

- **Detectors:** fall/collapse, physical altercation, abnormal crowd movement. Alerts need a sustained pattern across several frames, so a single frame never triggers one.
- **Evidence:** every candidate incident stores an annotated snapshot, a short clip, a timestamp, the camera, a confidence value and verification metadata.
- **Dashboard:** live operations view, camera grid, incident register with filters, map, analytics, committee inbox, acknowledge/resolve actions, and a clearly labelled demo mode.
- **Real-time:** new incidents and status changes are pushed over a WebSocket, with a REST snapshot for reconnects.
- **Workflow hooks:** a persistent outbox and authenticated callbacks let an external workflow (n8n) report notification, acknowledgement and escalation state back to the API.

## Tech stack

| Layer | Technology |
|---|---|
| Computer vision | Ultralytics YOLOv8 pose, ByteTrack, OpenCV, NumPy |
| Backend | FastAPI, SQLAlchemy, SQLite, Pydantic v2, httpx |
| Frontend | React 18, Vite, TypeScript, Tailwind, Recharts, Leaflet |
| Automation | n8n webhook workflow (in progress) |
| Hosting (demo) | Render (Web Service + Static Site), optional Cloudflare Tunnel |

## Repository layout

```text
backend/        FastAPI app, workflow outbox, migrations, tests
frontend/       React dashboard
part2/          Computer-vision pipeline (sentinel_ai/), detectors, model weights, tuning guide
automation/n8n/ n8n workflow export
docs/contracts/ Versioned incident schema, example payload, workflow callback contract
```

---

## Quick start (local, Windows PowerShell)

Python **3.11** is recommended. The backend pins package versions that do not support newer Python releases.

```powershell
# from the project root
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
cd backend
python run.py
```

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

In a second terminal, start the dashboard:

```powershell
Copy-Item frontend\.env.example frontend\.env.local
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open `http://localhost:5173`. In `frontend/.env.local`, set `VITE_USE_MOCK=false` to use the real backend, or keep `true` for an offline demo with sample data.

### Turn on the AI pipeline (optional, needs more RAM)

```powershell
pip install ultralytics
# in backend\.env set:  ENABLE_PIPELINE=true
cd backend
python run.py
```

The pipeline reads videos from `data/videos/` first, then `part2/data/videos/`. Footage is not committed to this repository (see [Data and licensing](#data-and-licensing)). To run the detector on one file without the backend, see `part2/sentinel_ai/run.py` and `part2/sentinel_ai/TUNING_GUIDE.md`.

---

## Configuration

Copy `backend/.env.example` to `backend/.env`. Never commit `.env` files or real secrets.

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` or `production`. Production requires the three secrets below to be 32+ characters. |
| `INTERNAL_API_TOKEN` | Bearer token the AI pipeline and workflow callbacks use to call internal endpoints. |
| `APP_DASHBOARD_TOKEN` | Token for dashboard actions. Must match `VITE_DASHBOARD_TOKEN` in the frontend build. |
| `APP_ADMIN_USERNAME` / `APP_ADMIN_PASSWORD` | Demo admin login. |
| `DATABASE_URL` | Defaults to `sqlite:///./sentinelai.db`. |
| `MEDIA_DIR` | Where snapshots and clips are stored and served under `/media/`. |
| `CORS_ORIGINS` | Comma-separated dashboard origins, no trailing slash. Must match the dashboard URL exactly. |
| `ENABLE_PIPELINE` | `true` starts the AI pipeline inside the backend. |
| `N8N_ENABLED`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET`, `N8N_TIMEOUT_SECONDS` | Outbound n8n delivery. Keep disabled until a workflow is configured. |

Frontend (`frontend/.env.local`, or build-time variables on the host):

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend base URL, no trailing slash. |
| `VITE_USE_MOCK` | `true` = offline sample data, `false` = live backend. |
| `VITE_DASHBOARD_TOKEN` | Must equal the backend's `APP_DASHBOARD_TOKEN`. It is bundled into the public JavaScript, so treat it as demo-grade, not real security. |

---

## Deploy on Render

**Backend (Web Service)**

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Env | `PYTHON_VERSION=3.11.9`, `APP_ENV=production`, the three secrets (32+ chars each), `CORS_ORIGINS=<dashboard URL>`, `ENABLE_PIPELINE=false`, `N8N_ENABLED=false` |

**Frontend (Static Site)**

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |
| Env | `VITE_API_URL=<backend URL>`, `VITE_USE_MOCK=false`, `VITE_DASHBOARD_TOKEN=<same as APP_DASHBOARD_TOKEN>` |

Deploy the backend first, then the frontend, then set `CORS_ORIGINS` on the backend to the frontend URL. After changing any `VITE_` variable, redeploy the static site, because those values are read at build time.

**Free-plan limits:** the backend sleeps after ~15 minutes idle, the SQLite file and media folder reset on restart, and 512 MB of RAM is not enough for the AI pipeline.

### Full AI mode (laptop + tunnel)

Run the backend with `ENABLE_PIPELINE=true` on a laptop, expose it with `cloudflared tunnel --url http://localhost:8000`, point the dashboard's `VITE_API_URL` at the tunnel address, and set the backend's `CORS_ORIGINS` to the dashboard URL. The quick-tunnel address changes each run, and the laptop must stay on.

---

## API overview

| Endpoint | Purpose |
|---|---|
| `GET /api/health`, `GET /api/cameras`, `GET /api/stats` | Status, cameras, analytics |
| `GET /api/incidents`, `GET /api/incidents/{id}` | Incident list (filterable) and detail |
| `GET /api/incidents/snapshot` | Reconnect-safe snapshot |
| `PATCH /api/incidents/{id}` | Update status/notes (dashboard token) |
| `POST /api/incidents/{id}/acknowledge`, `/resolve` | Lifecycle actions |
| `GET /api/incidents/{id}/workflow` | Workflow and notification state |
| `POST /api/internal/incidents` | Ingest an incident from the AI pipeline (internal token) |
| `POST /api/internal/incidents/{id}/workflow-events` | Workflow callbacks (internal token) |
| `POST /api/simulate` | Create a clearly labelled simulated incident |
| `GET /api/stream/{camera_id}` | MJPEG camera stream |
| `GET /media/...` | Evidence snapshots and clips |
| `WS /ws/incidents` | Live `incident.created`, `incident.updated`, `workflow.updated` events |

Incident types: `fall_collapse`, `physical_altercation`, `abnormal_crowd_movement` (the backend also accepts `vehicle_accident`). The versioned schema and example payload are in [`docs/contracts/`](docs/contracts/). Every incident carries a `source` field (`ai_detection` or `simulation`) so simulated events are never presented as real detections.

---

## Testing

```powershell
cd backend
python -m pytest tests -q
cd ..
python -m pytest part2\sentinel_ai\tests -q
npm --prefix frontend run build
```

Record your own results here once you have run them. Detection accuracy has not been formally measured on a labelled dataset; do not treat the sample videos as an accuracy benchmark.

---

## Status and limitations

Be explicit about what is real in a demo:

| Area | State |
|---|---|
| Dashboard, backend, database, live WebSocket updates | Working |
| Acknowledge and resolve, incident filters, map, analytics | Working (backend-persisted) |
| Simulated incidents | Working, always labelled as simulation |
| AI detection on sample videos | Working locally; **off** on free hosting (RAM limit) |
| n8n routing, Telegram alerts, timed escalation | **In progress.** The backend outbox and callbacks exist, but the workflow export is minimal. |
| Real operator login | **Not connected yet** |
| Evidence on hosted backend | Stored on local disk, so it is lost on restart. Persistent storage is planned. |
| Production authentication | **No.** Demo credentials and a static dashboard token are not production-grade. |

## Responsible use

- Authorized, prerecorded or simulated footage only.
- No facial recognition and no person identification. Tracks are anonymous IDs.
- Human-in-the-loop: the system raises candidates for operator review. It does not dispatch emergency services, and notifications must not claim that anyone has been dispatched unless that actually happened.

## Data and licensing

Sample footage is described in `part2/data/videos/SOURCES.md`. `cam_01` to `cam_03` come from third-party research sources that do not permit redistribution, so they are excluded from this repository by `.gitignore`. Obtain them from the original sources listed there, or generate synthetic clips with `part2/data/sample_generator.py`. `cam_04` (OpenCV sample) is Apache 2.0.

## Team

<!-- Add names and roles -->
