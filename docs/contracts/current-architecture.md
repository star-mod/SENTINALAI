# SentinelAI API and database baseline

This snapshot documents the archive before the workflow integration changes.

## Existing HTTP and WebSocket routes

All HTTP routes use the `/api` prefix.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service and camera health |
| POST | `/auth/login` | Demo username/password check; returns a static demo token |
| GET | `/auth/me` | Returns the configured demo admin identity |
| GET | `/cameras` | List cameras |
| GET | `/cameras/{camera_id}` | Get a camera |
| POST | `/cameras` | Create a camera |
| PATCH | `/cameras/{camera_id}` | Update a camera |
| DELETE | `/cameras/{camera_id}` | Delete a camera |
| GET | `/incidents` | List/filter incidents |
| GET | `/incidents/{incident_id}` | Get an incident |
| POST | `/incidents` | Create a dashboard incident |
| PATCH | `/incidents/{incident_id}` | Update status or notes |
| GET | `/stats` | Incident analytics |
| POST | `/internal/incidents` | Ingest a CV incident (initially unauthenticated) |
| POST | `/simulate` | Create a demo incident |
| POST | `/evidence/upload` | Add an evidence URL reference |
| GET | `/evidence/{evidence_id}` | Get an evidence reference |
| GET | `/incidents/{incident_id}/evidence` | List evidence for an incident |
| GET | `/stream/{camera_id}` | MJPEG camera stream |
| GET | `/incident-video/{incident_type}` | Serve the configured clip |
| — | `/media/*` | Static media directory |
| WS | `/ws/incidents` | Broadcast `incident.created` and `incident.updated` |

## Existing SQLAlchemy tables

| Table | Existing columns |
|---|---|
| `cameras` | `id`, `name`, JSON-text `location`, `status`, `stream_url` |
| `incidents` | `id`, `camera_id`, `camera_name`, JSON-text `location`, `type`, `confidence`, `severity`, `timestamp`, `status`, `snapshot_url`, `clip_url`, `notes`, JSON-text `verification` |
| `evidence` | `id`, `incident_id`, `type`, `url`, `created_at` |
| `users` | `id`, `username`, `password`, `role`, `created_at` |

`Base.metadata.create_all()` creates missing tables, but does not add new
columns to an existing SQLite database. The integration migration therefore
uses additive SQLite `ALTER TABLE` statements and preserves existing rows.

The login endpoint and its static token are demo-only; they are not production
authentication.
