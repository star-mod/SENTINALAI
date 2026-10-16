# SentinelAI n8n integration handoff

## Current state

The existing local, untracked file `automation/n8n/sentinelai_incident_response.json` is an obsolete, inactive stub that returns HTTP 503. It is not an export of the Cloud workflow and must not be imported as the working incident handler. The operator reports that the Cloud workflow is unpublished; this repository cannot verify its current Cloud state. No production webhook request is part of local validation.

The local producer-to-backend contract is implemented as follows:

- `part2/sentinel_ai/pipeline.py` posts after a detector emits a temporally confirmed **candidate**, with generated media URLs, `X-Webhook-Secret`, a 5-second timeout, and no automatic retry.
- `POST /api/internal/incidents` requires `X-Internal-Token` matching `INTERNAL_INGEST_TOKEN`. Its required JSON fields include stable `event_id`, `camera_id`, `type`, `confidence`, `timestamp`, `snapshot_url`, and `clip_url`; the schema constrains incident types and confidence.
- New events return HTTP 201. Repeated `event_id` values return HTTP 200 and the original incident without a second WebSocket `incident.created` broadcast. n8n must gate notifications on the new-event response, not merely on any 2xx response.
- The restricted local gateway accepts only POST `/api/internal/incidents` and forwards the internal token to FastAPI. It does not change backend authentication.

For a local file source the producer makes `event_id` deterministic from camera, incident type, canonical file path, file size, modification time, and trigger frame. Replaying that frame yields the same key; another frame/type yields another key. A live/non-file source uses a fresh UUID because a frame location cannot be replayed reliably. A bounded per-worker cache suppresses repeat sends for the same key during that process run. After a worker restart, another n8n execution can occur; the actual Cloud flow must persistently dedupe before notifications. These keys are deduplication aids, not proof that a detection is a confirmed emergency.

## Contract blocker: workflow callbacks and state

This checkout has no `POST /api/internal/incidents/{incident_id}/workflow-events` or `GET /api/incidents/{incident_id}/workflow` route. It therefore has no authoritative callback body, supported callback event schema, callback authentication, or workflow-state response to implement. Do not guess these contracts. `notification.sent`, `notification.failed`, `escalation.triggered`, persisted acknowledgement checks, and timeout escalation remain blocked until the backend owner supplies and agrees to the exact routes and contracts. Never contact real emergency services; any eventual recipient must be a configured demo target.

## Configuration

Backend settings are read from `backend/.env` by FastAPI startup; the CV pipeline reads the same process environment when started through FastAPI. If the CV process is launched separately, provide these variables in that process environment too:

```dotenv
ENABLE_PIPELINE=false
INTERNAL_INGEST_TOKEN=<same-long-random-value-used-by-gateway-and-n8n>
N8N_WEBHOOK_URL=<non-production-n8n-webhook-url>
N8N_WEBHOOK_SECRET=<n8n-header-auth-secret>
```

`N8N_WEBHOOK_SECRET` is sent as `X-Webhook-Secret` by the CV pipeline. `INTERNAL_INGEST_TOKEN` is sent as `X-Internal-Token` by the gateway to FastAPI and must also be configured in the n8n HTTP Request credential/header for the backend request. Never put values in workflow JSON, logs, screenshots, or commits. Use placeholders in shared examples. Keep `ENABLE_PIPELINE=false` during maintenance.

## Safe local startup

Run each process in a separate Terminal, from the repository root:

1. Backend: `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
2. Gateway: `cd backend && python -m uvicorn app.local_gateway:app --host 127.0.0.1 --port 8001 --no-access-log`.
3. Only when an authorized controlled demo is ready, set `ENABLE_PIPELINE=true` and restart the backend. Do not run the fake worker continuously during n8n execution-count investigations.

Stop each foreground process with Ctrl+C in its own terminal. A Cloudflare Quick Tunnel URL can change each time it starts; use only the URL printed by the currently running tunnel. Point it at `http://127.0.0.1:8001`, never directly at port 8000. This document does not claim tunnel or Cloud connectivity has been tested.

## Controlled test procedure

Use a local backend/gateway and a non-production n8n workflow with a demo recipient. First keep `ENABLE_PIPELINE=false`; submit one synthetic candidate to the gateway with a configured test token. Repeat exactly the same JSON and `event_id`: expect 201 then 200 with the same incident ID. In n8n, notify only when the HTTP response is 201; the duplicate response must not notify. Check the backend incident list for one record. Do not test against the production webhook or recipient.

Run focused local tests from the repository root (the CV suite needs `part2/requirements.txt`; backend tests need `backend/requirements.txt`):

```sh
python -m pytest part2/sentinel_ai/tests/test_pipeline_webhook.py
cd backend && python -m pytest tests/test_api.py -k 'internal_ingest'
cd backend && python -m pytest tests/test_local_gateway.py
```

The local tests use a mocked HTTP client for CV delivery and FastAPI's in-process test client for backend/gateway behavior. They do not import a workflow into n8n or test Cloudflare, Telegram, credentials, callbacks, or production behavior.

## Diagnostics and rollback

- Correlate the CV log line by camera/type and event time; never log request headers or bodies. The pipeline logs delivery failure by exception class and does not retry automatically.
- In the n8n execution view, inspect the webhook execution time, response status, and sanitized node output. The historical reason for prior high execution counts is unconfirmed; looping footage is a plausible code path, not historical proof. Cloud execution records and local process logs at matching times are needed to establish cause.
- To stop new CV submissions, keep/set `ENABLE_PIPELINE=false` and restart FastAPI only during an approved maintenance window. Pause/unpublish the Cloud workflow separately. Stop gateway/tunnel processes with Ctrl+C in their respective terminals.
- To revert source changes after review, use `git revert <integration-commit>`; do not remove the local `.env`, database, or video assets. The added `incident_events` table is additive and safe to leave in a local SQLite database.

## Remaining owners

- **Backend:** publish callback and workflow-state routes, exact schemas/authentication, and acknowledgement semantics.
- **n8n:** adapt the actual Cloud workflow to the required `event_id`, gate notifications on HTTP 201, and configure a demo-only recipient after callback contracts are agreed.
- **CV:** confirm source-video provenance and validate stable file/frame identity against intended demo behavior.
- **Operator:** use a test workflow and current tunnel URL for one controlled integration test; do not publish or enable the live pipeline until review.
