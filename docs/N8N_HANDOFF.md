# SentinelAI n8n Integration Handoff

## Status and safety

The checked-in `automation/n8n/sentinelai_incident_response.json` is an inactive contract-blocked stub. Its webhook responds with HTTP 503; it does not persist incidents, notify Telegram, or post workflow callbacks. It is not the Cloud workflow described by the operator and must not be activated as a working incident handler.

The operator reports that the Cloud workflow `v1.0.0 — Secure Incident Ingestion` was previously published and tested, has since been unpublished, and has Webhook and HTTP Request nodes. The reported Webhook receives an authenticated POST; the HTTP Request forwards the candidate through the tunnel to the gateway. Those Cloud node settings are not present in this repository and were not independently verified. Keep it unpublished until repeated executions, the event identity contract, and the camera/video mapping are resolved. Never send real emergency-service notifications; every detector result remains an unverified candidate.

## Architecture and responsibilities

Intended flow: CV pipeline → authenticated n8n Cloud webhook → HTTP Request → Cloudflare Quick Tunnel → restricted local gateway → FastAPI ingestion API → dashboard reads backend incidents.

- **n8n integration owner:** Cloud workflow configuration, candidate routing, demo-only notifications, workflow execution monitoring, and handoff.
- **CV pipeline owner:** camera/video provenance and mapping, detector thresholds/cooldown, and delivery from `part2/sentinel_ai/pipeline.py`.
- **Backend owner:** ingestion identity/idempotency and workflow callback/state APIs.
- **Dashboard owner:** display and filtering of backend incident records.

The intended Cloudflare topology and the Cloud workflow node configuration are operator-reported. The repository contains the local gateway at `backend/app/local_gateway.py`; it accepts only `POST /api/internal/incidents`, forwards to the local FastAPI API, and passes the internal token header through. Cloudflare Quick Tunnel public addresses can change; use the address currently shown by the running `cloudflared` process, and do not put it or credentials in repository documentation.

## Verified producer and current backend contract

`CameraWorker._handle_incident` is called only after a detector returns a temporally confirmed `Detection`. It saves a snapshot, schedules a clip, maps detection and camera metadata, then starts one background HTTP POST to the configured n8n webhook. The request has a 5-second timeout and sends `X-Webhook-Secret` from `N8N_WEBHOOK_SECRET`. HTTP/network failures are logged by exception type and return `False`; there is no automatic retry or durable delivery record.

Current producer JSON fields are:

```json
{
  "camera_id": "cam_01",
  "camera_name": "<configured camera name>",
  "location": {"lat": 0.0, "lng": 0.0, "label": "<configured label>"},
  "type": "fall_collapse",
  "confidence": 0.91,
  "severity": "high",
  "timestamp": "<UTC ISO-8601 timestamp>",
  "snapshot_url": "/media/snapshots/<generated file>",
  "clip_url": "/media/clips/<generated file>",
  "notes": "<detector description>",
  "verification": {"window_seconds": 2.5, "frames_confirmed": 22, "frames_required": 15}
}
```

The current payload has **no `event_id`**. `InternalIncident` in `backend/app/schemas.py` has no `event_id`, and `POST /api/internal/incidents` creates an incident with a backend-generated ID; the route has no event-key idempotency behavior. Repeated submissions can therefore create separate records. Do not add speculative fields or claim duplicate safety until the backend owner agrees and implements an identity/idempotency contract.

The verified backend ingestion route is `POST /api/internal/incidents`, protected by `X-Internal-Token` matching backend `INTERNAL_INGEST_TOKEN`. A successful new ingestion returns HTTP 201 and an incident response. The local gateway forwards this header; it does not authenticate n8n itself. Keep the internal token and webhook secret in their respective environment/credential stores, never in workflow exports, source files, or logs.

The current backend does **not** define `POST /api/internal/incidents/{incident_id}/workflow-events`, `GET /api/incidents/{incident_id}/workflow`, or a workflow callback contract. Therefore exact callback event payloads, accepted event names, callback authentication, workflow-state response shape, and callback idempotency are unavailable. Do not build callback nodes until the backend owner publishes and agrees to that contract.

## Repeated execution investigation

Repository evidence establishes a credible repeat source, but does not prove the source of the historical Cloud execution count:

- `CameraWorker.run` loops a video back to frame zero when it reaches EOF.
- Detector cooldown is configured to 20 seconds and applied per detector/camera. It suppresses a continuous trigger only during that interval; it is not a persistent event deduplicator.
- Every detector trigger calls `_handle_incident`, which starts a new daemon thread that POSTs to the webhook. There is no stable event key, global cooldown, request retry loop, or durable outbox in this path.
- FastAPI starts the pipeline only when `ENABLE_PIPELINE=true`. The ignored local `backend/.env` currently has `ENABLE_PIPELINE=false`, verified without reading or reporting any other environment values. No listener on port 8000 or 8001 was active during this audit. Preserve the maintenance setting; changing it could start the CV workers on a later backend launch.
- `backend/scripts/fake_ai_worker.py` posts random synthetic events directly to FastAPI every 15 seconds when manually run. It does not call the n8n webhook in its own code, so it is not by itself evidence of Cloud execution triggers.

Thus, if the backend pipeline was running with detections and the Cloud webhook was published, looping footage plus the short cooldown could produce recurring n8n executions. This is a **moderate-confidence code-based explanation**, not proof of the historical executions. Attribution still requires Cloud execution timestamps/node inputs and local process/log evidence. Do not add automatic retries; there is no verified event idempotency contract.

## Configuration and safe activation

The FastAPI startup loads `.env` and the pipeline is disabled by default when `ENABLE_PIPELINE` is absent. The ignored `backend/.env` currently has `ENABLE_PIPELINE=false`, verified without reading or reporting any other environment values. Preserve that maintenance setting and do not commit the file. CV-to-n8n delivery requires both `N8N_WEBHOOK_URL` and `N8N_WEBHOOK_SECRET`; neither has a hardcoded destination fallback. The pipeline sends the secret as `X-Webhook-Secret` and skips delivery if either setting is missing. The local gateway/backend use `INTERNAL_INGEST_TOKEN` for backend ingress, with the header `X-Internal-Token`. The environment example contains placeholders only.

Cloud n8n credentials are operator-managed. Per the operator's description, configure Webhook Header Auth for the expected `X-Webhook-Secret` header and configure the HTTP Request node to forward the candidate body to the current Cloudflare tunnel URL plus the restricted ingestion path. Store the internal token in an n8n credential or protected environment variable and attach it as `X-Internal-Token`. Never paste either value into exported JSON or this repository. Confirm the actual Header Auth credential and HTTP Request node settings in the n8n UI; they cannot be verified from the checked-in stub.

Before activation:

1. Keep the Cloud workflow unpublished and `ENABLE_PIPELINE=false` while investigating previous executions.
2. Confirm the camera identifiers, location metadata, prerecorded video provenance, and whether test events are generated by the CV pipeline or a manually started fake worker.
3. Agree on a stable producer `event_id`, backend uniqueness/idempotency behavior, and duplicate response behavior with the backend owner.
4. Implement and document callback/state routes and their exact authentication, payload, response, and retry semantics before adding those workflow nodes.
5. Test with a non-production n8n workflow and synthetic input, first one controlled event at a time. Verify a single execution and backend record; inspect Cloud execution history after every trial.
6. Enable the CV pipeline only for an authorized, controlled demo, then publish the Cloud workflow only after the test chain is verified. Keep notification recipients demo-only.

To confirm an event reached FastAPI, capture the successful ingestion response's backend-generated incident ID and query `GET /api/incidents/{incident_id}` or the incident list. Correlate the request time, response status/ID, and camera/type with FastAPI access logs and the n8n execution record; redact request bodies and credentials from shared logs. Confirm `camera_id`, `type`, timestamp, and evidence URLs against the source test event. Do not infer the source camera from location text alone.

## Verification performed and remaining

- Passed: mocked CV webhook tests cover payload mapping, header/timeout, request failure handling, and missing URL/secret behavior. They send no real requests.
- Passed: backend ingestion auth tests (`3 passed`) cover valid, missing, invalid, and unset token behavior.
- Passed: `git diff --check` and cached diff check.
- Not verified: importing or executing this JSON in n8n, Cloud workflow node settings, credentials, activation state, live Cloudflare connectivity, Telegram delivery, backend-to-Cloud end-to-end delivery, historical execution cause, event deduplication, or workflow callbacks/state. No production webhook request was sent.

After the backend identity and callback contracts exist, run controlled synthetic cases for a high-priority candidate, medium-priority candidate, uncertain candidate, invalid body, same `event_id` twice, notification failure, callback failure, and an acknowledgement before/after the configured timeout. Verify persisted state before any demo escalation. These cases are not currently supported by the checked-in workflow stub or backend contracts; do not simulate them by activating the production Cloud workflow.

## Handoff checklist

- [ ] Keep the workflow unpublished until the source and recurrence are understood.
- [ ] Check n8n execution history for trigger time, request body shape (redact sensitive values), response code, and node that starts the execution.
- [ ] Confirm whether the backend pipeline or fake worker was running at those times; inspect pipeline/camera logs without recording credentials or request bodies.
- [ ] Reconcile `ENABLE_PIPELINE` with the desired maintenance state before restarting FastAPI.
- [ ] Resolve backend event ID/idempotency and callback/state API contracts.
- [ ] Verify current tunnel address and local gateway/backend availability using a synthetic, controlled test only.
- [ ] Test one event and verify exactly one execution, notification attempt, and backend incident before increasing test volume.
- [ ] Keep all notification targets demo-only; never contact emergency services.
- [ ] Exclude `.env` files and `part2/data/videos/watermarked_preview.mp4` from staging. Review intended files individually; do not use `git add .`.

Keep the ignored `backend/.env` and demo video out of version control. The contract-blocked JSON is intentionally nonfunctional; do not present it as the published Cloud workflow.
