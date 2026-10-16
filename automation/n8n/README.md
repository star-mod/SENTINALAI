# SentinelAI n8n incident response

## Implementation status: blocked on backend contract

The checked-in JSON is syntactically valid but is an inactive contract-blocked stub; n8n import has not been verified. Its POST webhook returns HTTP 503 with `BACKEND_CONTRACT_UNAVAILABLE`. It does not persist incidents, send notifications, or emit workflow callbacks. Do not treat it as the Cloud workflow or activate it as an incident handler while the required backend contracts are unavailable.

No credentials or secrets are required for this blocked workflow. Do not activate it as the incident handler. The webhook path after import is `/webhook/sentinelai/incident-response` (or n8n's test URL while using test mode).

## Repository verification

The available backend files were inspected at implementation time:

- `backend/app/schemas.py` defines `InternalIncident` with `camera_id`, optional `camera_name`, optional `location`, `type`, `confidence`, optional `severity`, `timestamp`, `snapshot_url`, `clip_url`, `notes`, and optional `verification`. It does **not** define `event_id`.
- `backend/app/routes/api.py` defines `POST /api/internal/incidents`, which creates an incident with a backend-generated ID. It does not show an idempotency key or duplicate response contract.
- The inspected API routes do not define `POST /api/internal/incidents/{incident_id}/workflow-events` or `GET /api/incidents/{incident_id}/workflow`.
- `workflow-callbacks.md` was not found in the repository.
- The available backend schema does not specify authentication for those callback routes. The inspected incident routes contain no authentication dependency.

Consequently, callback event payload fields, callback authentication, supported event types, workflow-state response shape, and the promised `event_id` ingestion semantics cannot be verified here. This README does not infer or invent them.

## Contract required to continue

Please add or point to the authoritative backend contract covering all of the following:

1. The incident candidate request schema, including where the stable `event_id` is supplied.
2. The `POST /api/internal/incidents` idempotency behavior for repeated `event_id` values, including response status/body on duplicates.
3. Exact callback request bodies and accepted event names for `notification.sent`, `notification.failed`, and `escalation.triggered`.
4. Callback authentication method and credential/header format.
5. Exact response shape and state values returned by `GET /api/incidents/{incident_id}/workflow`.
6. Whether callback retries are idempotent and how callback failure should be surfaced.

Once documented and present in the checkout, the intended workflow can validate and normalize the agreed candidate, deduplicate by the backend-supported stable ID, persist it once, route only candidate-level demo notifications or human review, emit the exact documented callback events, and recheck persisted workflow state before any demo escalation. Detections will remain unverified candidates; real emergency services will not be contacted.

## Testing status

The seven requested behavioral cases (high priority, medium priority, uncertain, invalid, duplicate, callback failure, and notification failure) cannot be meaningfully exercised until the input, persistence, callback, and state contracts exist and n8n plus any demo notification credentials are available. The current workflow's intended observable behavior is a 503 response for every POST; it does not claim successful workflow processing. Import and n8n execution have not been verified in an n8n instance.
