# SentinelAI n8n Integration Handoff

## Status and boundaries

The CV-to-backend ingestion path now carries a stable `event_id` for file-backed video frames, and the backend stores it in an additive `incident_events` ledger. New ingestion returns 201; a repeated key returns 200 with the original incident and does not broadcast another `incident.created` event. All detections remain unverified candidates. No emergency service is contacted.

The existing local, untracked file `automation/n8n/sentinelai_incident_response.json` is an obsolete inactive 503 stub, not an export of the Cloud workflow. The operator reports the Cloud workflow is unpublished; this was not independently verified in n8n. Keep it unpublished during maintenance. Backend workflow callback and workflow-state routes are absent, so notification outcome callbacks and acknowledgement-based escalation are not implemented.

## Architecture and ownership

Intended flow: CV pipeline → authenticated n8n Cloud webhook → Cloud HTTP Request → Cloudflare Quick Tunnel → restricted gateway on 127.0.0.1:8001 → FastAPI on 127.0.0.1:8000 → dashboard.

- **CV owner:** detector thresholds, media provenance, event key behavior, webhook delivery.
- **Backend owner:** authenticated ingestion and idempotency; still must provide callback/state contracts.
- **n8n owner:** Cloud workflow, dedupe-aware notification routing, demo recipient, execution monitoring.
- **Dashboard owner:** display backend incident records.

The repository gateway accepts only POST `/api/internal/incidents`, forwards to FastAPI and passes `X-Internal-Token`; backend ingestion independently validates the token. A Cloudflare Quick Tunnel URL can change each run. Point it only at port 8001, not the backend port. No current tunnel or Cloud request was made for this work.

## Producer and backend contract

`CameraWorker._handle_incident` runs after a detector returns a temporally confirmed `Detection`. It saves a snapshot, schedules a clip in the ring buffer, then starts one daemon thread to POST the candidate with a 5-second timeout. The configured `N8N_WEBHOOK_SECRET` is sent as `X-Webhook-Secret`. Failure is logged without request body or secret; there is no automatic retry or durable producer outbox.

Payload fields:

```json
{
  "event_id": "evt_<stable-or-random-key>",
  "camera_id": "cam_01",
  "camera_name": "<configured camera name>",
  "location": {"lat": 0.0, "lng": 0.0, "label": "<configured label>"},
  "type": "fall_collapse",
  "confidence": 0.91,
  "severity": "high",
  "timestamp": "<ISO-8601 timestamp>",
  "snapshot_url": "/media/snapshots/<generated file>",
  "clip_url": "/media/clips/<generated file>",
  "notes": "<detector description>",
  "verification": {"window_seconds": 2.5, "frames_confirmed": 22, "frames_required": 15}
}
```

`event_id` is required and restricted to 1–128 characters matching the backend's safe identifier pattern. Local files use a SHA-256-derived key over camera ID, type, canonical source path, file size, modification time, and frame index. The same replayed frame gets the same ID; distinct frame or type gets a different ID. Non-file/live sources get a fresh UUID for each candidate. A bounded per-worker cache suppresses repeat sends for the same key during a process run. After restart, another webhook execution can occur, so the Cloud workflow must still persistently dedupe before notifications. This does not suppress distinct frame locations or guarantee durable delivery.

`POST /api/internal/incidents` requires `X-Internal-Token` matching `INTERNAL_INGEST_TOKEN`. It returns 201 for a new incident and 200 with the original incident for an already-recorded `event_id`. The backend does not include `event_id` in the dashboard incident schema. The n8n workflow must forward it and only notify for a new 201 response; treat 200 as a duplicate. The fake worker now generates a new UUID key for each synthetic event.

The code does not define `POST /api/internal/incidents/{incident_id}/workflow-events` or `GET /api/incidents/{incident_id}/workflow`. Exact callback fields, supported callback event names, authentication, state response, and retry/acknowledgement semantics are therefore unavailable. Do not add callback nodes or escalation logic until the backend owner provides the agreed contract. Current requirements to report `notification.sent`, `notification.failed`, or `escalation.triggered` remain blocked for this reason.

## Configuration and safe operation

FastAPI loads `backend/.env`. When started through FastAPI, the CV pipeline reads the same environment. A separately launched CV process needs the same variables in its own environment.

```dotenv
ENABLE_PIPELINE=false
INTERNAL_INGEST_TOKEN=<long-random-shared-value>
N8N_WEBHOOK_URL=<non-production-webhook-url>
N8N_WEBHOOK_SECRET=<n8n-header-auth-secret>
```

`INTERNAL_INGEST_TOKEN` is used by the local gateway/n8n caller as `X-Internal-Token`; backend checks it using constant-time comparison. `N8N_WEBHOOK_SECRET` is only for CV-to-n8n `X-Webhook-Secret`. Never commit `.env` or paste secrets into logs, screenshots, exports, or docs. The ignored local `.env` maintenance setting was verified as `ENABLE_PIPELINE=false`; no other environment values were inspected or reported.

Safe local commands, each in its own terminal:

```sh
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd backend && python -m uvicorn app.local_gateway:app --host 127.0.0.1 --port 8001 --no-access-log
```

Keep `ENABLE_PIPELINE=false` unless an authorized controlled demo is ready. Start/stop Cloudflare separately and use the currently printed URL; Ctrl+C stops each foreground process. Do not run the recurring fake worker during execution-count investigation.

## Duplicates, failures, and verification

The prerecorded-video loop resets to frame zero. Local detector cooldown is 20 seconds per detector/camera; it is not the idempotency mechanism. Stable file/frame IDs plus the bounded worker cache suppress same-frame posts within a run, and backend uniqueness prevents repeat incident rows across process restarts/retries. A webhook execution can still occur after restart, so n8n must dedupe before notifying. The webhook sender performs one attempt only; failed delivery is observable in CV logs but can be lost because there is no outbox/retry. Do not add uncontrolled retries. The historical cause of prior ~500 n8n executions is not established; looped footage is plausible, not verified. Determining it requires timestamped n8n executions/node inputs and matching local backend/CV process logs.

Run local mocked/in-process checks:

```sh
python -m pytest part2/sentinel_ai/tests/test_pipeline_webhook.py
cd backend && python -m pytest tests/test_api.py -k 'internal_ingest'
cd backend && python -m pytest tests/test_local_gateway.py
```

For a controlled non-production test, submit one synthetic payload through port 8001 with a test token and then resubmit the identical `event_id`. Expect 201 then 200, the same incident ID, one backend record, and no duplicate notification (n8n must gate on 201). Use only a demo recipient. Inspect n8n execution timestamps/node status and correlate with backend incident ID and sanitized server logs; never record request bodies or credentials. No real Cloud workflow, tunnel, Telegram delivery, callback, or end-to-end request is claimed verified here.

Before activation, the backend owner must add and document callback/state routes and acknowledgement semantics. The n8n owner must adapt the actual Cloud workflow to preserve `event_id`, gate duplicates, and use demo-only notifications. The CV owner must validate camera/video provenance and stable event identity. Keep the Cloud workflow unpublished and pipeline disabled until one controlled test succeeds and owners review it.

Rollback: set `ENABLE_PIPELINE=false` and restart FastAPI in an approved maintenance window; pause/unpublish the Cloud workflow separately; stop gateway/tunnel with Ctrl+C. If reverting source, use `git revert <integration-commit>` after review. The `incident_events` table is additive; do not delete local database or media files. Keep `backend/.env`, generated videos, and the obsolete 503 stub out of commits.
