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

Python 3.11 is recommended. From the workspace root, start the backend in
PowerShell:

```powershell
Set-Location C:\Users\anupa\Downloads\SENTINALAI-main
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
Set-Location backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API creates or incrementally migrates its SQLite database, seeds four cameras and six historical incidents, and creates local placeholder snapshots/clips under `backend/`. Existing records are preserved. OpenAPI is at `http://localhost:8000/docs`. Internal CV ingestion and workflow callbacks require `INTERNAL_API_TOKEN`; the sample `.env` value is for local demo use only. Dashboard status changes use the sample `APP_DASHBOARD_TOKEN`, also demo-only.

To enable n8n delivery, set `N8N_ENABLED=true`, `N8N_WEBHOOK_URL`, and
`N8N_WEBHOOK_SECRET` in `backend/.env`. A persistent outbox queues events
alongside each incident and retries webhook failures after commit. A webhook
2xx response means only that n8n accepted the event; Telegram delivery is not
guaranteed. See [the callback contract](docs/contracts/workflow-callbacks.md)
and the versioned [incident schema](docs/contracts/incident-event.schema.json).

To run the existing pipeline without rebuilding it, install
`../part2/requirements.txt` while in `backend/`, then set `ENABLE_PIPELINE=true`
in `backend/.env`; the pipeline uses the configured media directories and sends
the internal bearer token from that environment.

Camera clips are read from the ignored local folder `data/videos/` first, with existing `part2/data/videos/` files as fallback. The separately acquired research footage is not committed or redistributed. Check `part2/data/videos/SOURCES.md` for provenance and usage conditions before using or sharing any downloaded clip.

In a second terminal:

```powershell
Set-Location C:\Users\anupa\Downloads\SENTINALAI-main
if (-not (Test-Path frontend\.env.local)) { Copy-Item frontend\.env.example frontend\.env.local }
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
curl.exe -X POST http://localhost:8000/api/internal/incidents -H "Authorization: Bearer local-dev-internal-token" -H "Content-Type: application/json" -d "{`"camera_id`":`"cam_01`",`"camera_name`":`"Central Plaza - North`",`"location`":{`"lat`":12.9716,`"lng`":77.5946,`"label`":`"Central Plaza`"},`"type`":`"fall_collapse`",`"confidence`":0.91,`"timestamp`":`"2026-10-10T10:00:00Z`",`"snapshot_url`":`"/media/snapshots/cam_01_fall_collapse.jpg`",`"clip_url`":`"/media/clips/cam_01_fall_collapse.mp4`",`"verification`":{`"window_seconds`":2.5,`"frames_confirmed`":38,`"frames_required`":30}}"
curl.exe http://localhost:8000/api/stream/cam_01
```

Evidence files are served below `/media/`; for example `http://localhost:8000/media/snapshots/cam_01_fall_collapse.jpg`. The incident WebSocket is `ws://localhost:8000/ws/incidents`, broadcasting `incident.created` and `incident.updated` messages. MJPEG streams are multipart responses at `/api/stream/{camera_id}`.

`GET /api/incidents/snapshot` supplies a reconnect snapshot. The socket also
broadcasts `workflow.updated`. Internal endpoints reject requests without the
configured producer token. The login endpoint and default demo credentials are
not production-grade authentication; configure secrets and place the service
behind a production identity/access layer before deployment.

The detail drawer uses `/api/incident-video/{type}` to stream the matching local prerecorded MP4 inline with byte-range seeking.

## Checks

```

Authenticate the CV ingest endpoint from PowerShell with the configured token:

```powershell
$env:INTERNAL_API_TOKEN = "local-dev-internal-token"
$headers = @{ Authorization = "Bearer $env:INTERNAL_API_TOKEN" }
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/internal/incidents" -Headers $headers -ContentType "application/json" -Body (Get-Content .\incident.json -Raw)
```

The dashboard has a local demo token configured in `frontend/.env.example`.
Match its `VITE_DASHBOARD_TOKEN` to `APP_DASHBOARD_TOKEN` in the backend
environment when changing the demo value.powershell
Push-Location backend
python -m pytest tests -q
Pop-Location
npm --prefix frontend run build
```

For detector configuration and threshold tuning in the existing CV package, see [part2/sentinel_ai/TUNING_GUIDE.md](part2/sentinel_ai/TUNING_GUIDE.md). Keep all video inputs authorized and prerecorded/simulated for this prototype.