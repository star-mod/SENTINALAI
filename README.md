# SentinelAI Control Room

Local-first public safety incident demo for authorized prerecorded or simulated feeds. The dashboard and API support operator review; they do not identify people or take autonomous action. `part2/` has been updated to the latest Part 2 drop, including real camera footage in `part2/data/videos/` (see its SOURCES.md for provenance and usage terms).

## Project Structure

```text
backend/                     FastAPI app, tests, demo worker, requirements, runtime data
frontend/                    React 18 + Vite + TypeScript dashboard
data/videos/                 Shared local video inputs (ignored by Git)
part2/                       Existing project; not modified
```

## Run Locally

Python 3.11 is recommended. From the workspace root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
Set-Location backend
python -m uvicorn app.main:app --reload --port 8000
```

The API creates its SQLite database, four cameras, six historical incidents, and local placeholder snapshots/clips under `backend/`. OpenAPI is at `http://localhost:8000/docs`. The pipeline is disabled by default. To run the existing pipeline without modifying it, install `../part2/requirements.txt` while in `backend/`, then set `ENABLE_PIPELINE=true` in `backend/.env`; the API imports its `PipelineManager` with the existing `part2/sentinel_ai` configuration.

Set `INTERNAL_INGEST_TOKEN` in `backend/.env` to a long random value before using direct backend ingestion. `POST /api/internal/incidents` requires that value in the `X-Internal-Token` header. For CV-to-n8n delivery, explicitly set `N8N_WEBHOOK_URL` and `N8N_WEBHOOK_SECRET` in `backend/.env`; the pipeline sends the secret in `X-Webhook-Secret` and skips delivery if either setting is absent. No webhook destination is hardcoded as a fallback. Replace placeholders from `backend/.env.example`; do not use them as credentials. If running the CV pipeline outside the backend process, make the same variables available in that process environment.

The CV pipeline posts only when a detector produces a temporally confirmed detection and both n8n settings are configured. It first writes the snapshot and schedules the clip using its existing ring buffer, then maps those generated `/media/...` URLs into the webhook payload. The payload includes a required `event_id`: local file-backed sources derive it from camera, type, source file metadata, and triggering frame so replaying the same frame deduplicates; non-file/live sources use a fresh UUID per candidate. A bounded per-worker cache suppresses repeat posts for the same ID while that worker runs. The backend persists this key with the incident and returns `201` for a new event or `200` with the original incident for a duplicate. Failed webhook delivery is logged without the secret or request body and is not automatically retried; the pipeline has no durable delivery queue. After a worker restart, the same webhook may execute again; the n8n flow must persistently dedupe before notification.

The backend requires `event_id` on direct internal ingestion too. Keep the `event_id` in the n8n HTTP Request body when forwarding it; use the backend's `201` versus `200` response to distinguish a fresh record from a duplicate before any notification attempt. The backend workflow callback and workflow-state routes are not implemented in this checkout, so callback/status recording and acknowledgement-based escalation are blocked pending an agreed backend contract.

### Optional local gateway for n8n Cloud

Keep the backend running on port 8000. In a second terminal, start the narrow local gateway from the `backend/` directory:

```powershell
python -m uvicorn app.local_gateway:app --host 127.0.0.1 --port 8001 --no-access-log
```

The gateway accepts only `POST /api/internal/incidents` and forwards it to the backend on port 8000, including the `X-Internal-Token` header. Point a separately configured Cloudflare Tunnel at `http://127.0.0.1:8001` and give n8n the tunneled webhook URL. Stop the gateway with Ctrl+C in its terminal. Stop the backend separately in its own terminal. The gateway does not replace the backend token check.

Camera clips are read from the ignored local folder `data/videos/` first, with existing `part2/data/videos/` files as fallback. The separately acquired research footage is not committed or redistributed. Check `part2/data/videos/SOURCES.md` for provenance and usage conditions before using or sharing any downloaded clip.

In a second terminal:

```powershell
Copy-Item frontend/.env.example frontend/.env.local
npm --prefix frontend ci
npm --prefix frontend run dev
```

Dashboard: `http://localhost:5173`. To use the live API, set `VITE_USE_MOCK=false` in `frontend/.env.local`. To run the dashboard independently/offline, keep it `true`; it loads six local records and generates a demo event about every 60 seconds. The Map uses standard OpenStreetMap tiles without an API key. Map tiles need an internet connection; camera markers and incident data remain local when offline.

## Demo Worker

With the API running, send a verified sample event every 15 seconds:

```powershell
python backend/scripts/fake_ai_worker.py
```

Choose another cadence or API address with `--interval 8 --base-url http://localhost:8000`.

## API Examples

```powershell
curl.exe http://localhost:8000/api/health
curl.exe http://localhost:8000/api/cameras
curl.exe "http://localhost:8000/api/incidents?status=new&type=fall_collapse&camera_id=cam_01"
curl.exe http://localhost:8000/api/incidents/inc_0001
curl.exe -X PATCH http://localhost:8000/api/incidents/inc_0001 -H "Content-Type: application/json" -d "{`"status`":`"acknowledged`",`"notes`":`"Operator reviewing evidence`"}"
curl.exe http://localhost:8000/api/stats
curl.exe -X POST http://localhost:8000/api/simulate -H "Content-Type: application/json" -d "{`"type`":`"fall_collapse`",`"camera_id`":`"cam_01`"}"
curl.exe -X POST http://localhost:8000/api/internal/incidents -H "Content-Type: application/json" -H "X-Internal-Token: <configured-token>" -d "{`"event_id`":`"evt_manual_demo_001`",`"camera_id`":`"cam_01`",`"camera_name`":`"Central Plaza - North`",`"location`":{`"lat`":12.9716,`"lng`":77.5946,`"label`":`"Central Plaza`"},`"type`":`"fall_collapse`",`"confidence`":0.91,`"timestamp`":`"2026-10-10T10:00:00Z`",`"snapshot_url`":`"/media/snapshots/cam_01_fall_collapse.jpg`",`"clip_url`":`"/media/clips/cam_01_fall_collapse.mp4`",`"verification`":{`"window_seconds`":2.5,`"frames_confirmed`":38,`"frames_required`":30}}"
curl.exe http://localhost:8000/api/stream/cam_01
```

Evidence files are served below `/media/`; for example `http://localhost:8000/media/snapshots/cam_01_fall_collapse.jpg`. The incident WebSocket is `ws://localhost:8000/ws/incidents`, broadcasting `incident.created` and `incident.updated` messages. MJPEG streams are multipart responses at `/api/stream/{camera_id}`.

The detail drawer uses `/api/incident-video/{type}` to stream the matching local prerecorded MP4 inline with byte-range seeking.

## Checks

```powershell
Push-Location backend
python -m pytest tests -q
Pop-Location
npm --prefix frontend run build
```

For detector configuration and threshold tuning in the existing CV package, see [part2/sentinel_ai/TUNING_GUIDE.md](part2/sentinel_ai/TUNING_GUIDE.md). Keep all video inputs authorized and prerecorded/simulated for this prototype.
