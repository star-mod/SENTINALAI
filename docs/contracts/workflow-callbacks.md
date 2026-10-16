# n8n workflow integration

Each CV detection gets a UUID-based `event_id` once, before evidence filenames
and the payload are created. The same payload (and ID) is used for the local
callback and HTTP submission. FastAPI requires that ID, persists it in
`incidents.event_id`, and enforces uniqueness with a SQLite unique index.
Repeating the same submission returns the existing incident; reusing the ID
for different incident data is rejected with `409 Conflict`. The additive
migration assigns `legacy_<incident-id>` IDs to existing rows without one.

Configure the backend with `N8N_ENABLED=true`, `N8N_WEBHOOK_URL`,
`N8N_WEBHOOK_SECRET`, and `N8N_TIMEOUT_SECONDS`. The API writes an outbox row
in the same transaction as the incident, then a background dispatcher sends
the contract event after commit. HTTP failures remain queued and retry with
exponential backoff (2 seconds, doubling up to 256 seconds). Outbound requests
include `Idempotency-Key: <event_id>` and
`X-Webhook-Secret: <N8N_WEBHOOK_SECRET>`. The secret is required when dispatch
is enabled. Non-local webhook URLs must use HTTPS; plain HTTP is allowed only
for localhost development.

This confirms delivery to the configured webhook endpoint only. It does not
guarantee Telegram delivery, exactly-once processing, or successful human
notification. n8n should deduplicate by idempotency key before triggering
non-idempotent actions.

## Authenticated callback

Send callbacks to `POST /api/internal/incidents/{incident_id}/workflow-events`
with `Authorization: Bearer <INTERNAL_API_TOKEN>` (or `X-Internal-Token`).
The JSON shape is:

```json
{
  "event_id": "n8n-execution-id:notification-sent",
  "type": "notification.sent",
  "timestamp": "2026-10-16T06:51:00Z",
  "responder_id": null,
  "details": { "channel": "telegram" }
}
```

Supported event `type` values:

* `notification.sent`
* `notification.failed`
* `acknowledgement.received` (include `responder_id`)
* `escalation.triggered`
* `workflow.completed` (requires the incident to be acknowledged)

Callback event IDs are idempotency keys. Repeating an event ID with the same
incident and type returns the already stored incident. A second distinct
acknowledgement is rejected. Notification failure callbacks never downgrade a
previous successful notification. Each callback is recorded in the
`workflow_audit` table. Queued webhook work is cancelled once an incident is
acknowledged or resolved so it is not automatically re-dispatched afterward.

`GET /api/incidents/{incident_id}/workflow` exposes workflow state and
dispatch attempts. `GET /api/incidents/snapshot` provides the initial REST
snapshot; the dashboard refreshes it on every WebSocket connection/reconnect.
Detection confidence is not used to assign incident severity. Newly ingested
CV events without an operator assessment start at `medium` with
`severity_verified=false`; an authenticated dashboard PATCH with a `severity`
value records the operator's assessment and marks it verified.

The optional live test uses `N8N_INTEGRATION_WEBHOOK_URL` and can be run with:

```powershell
$env:N8N_INTEGRATION_WEBHOOK_URL = "http://localhost:5678/webhook/sentinelai-test"
Push-Location backend
python -m pytest tests/test_n8n_local.py -q
Pop-Location
```
