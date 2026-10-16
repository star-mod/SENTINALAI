import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import main
from app.database import SessionLocal
from app.models import Evidence, Incident, WorkflowAudit, WorkflowOutbox
from app.services import workflow_service


INTERNAL_HEADERS = {"Authorization": "Bearer local-dev-internal-token"}
DASHBOARD_HEADERS = {"Authorization": "Bearer demo-admin-token"}
_created_incident_ids: set[str] = set()


@pytest.fixture(autouse=True)
def disable_n8n_for_workflow_tests(monkeypatch):
    monkeypatch.setenv("N8N_ENABLED", "false")
    _created_incident_ids.clear()
    yield
    with SessionLocal() as db:
        for incident_id in _created_incident_ids:
            db.execute(delete(WorkflowAudit).where(WorkflowAudit.incident_id == incident_id))
            db.execute(delete(Evidence).where(Evidence.incident_id == incident_id))
            db.execute(delete(WorkflowOutbox).where(WorkflowOutbox.incident_id == incident_id))
            incident = db.get(Incident, incident_id)
            if incident is not None:
                db.delete(incident)
        db.commit()


def incident_payload(**overrides):
    event_id = f"evt_test_{uuid.uuid4().hex}"
    payload = {
        "id": f"int_{uuid.uuid4().hex[:16]}",
        "event_id": event_id,
        "schema_version": "1.0",
        "camera_id": "cam_01",
        "type": "fall_collapse",
        "confidence": 0.91,
        "severity": "medium",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot_url": f"/media/snapshots/{event_id}.jpg",
        "clip_url": f"/media/clips/{event_id}.mp4",
        "verification": {"window_seconds": 2.5, "frames_confirmed": 36, "frames_required": 25},
        "source": "ai_detection",
        "detection_metadata": {"detector": "test"},
    }
    payload.update(overrides)
    return payload


def post_incident(client, payload):
    response = client.post("/api/internal/incidents", headers=INTERNAL_HEADERS, json=payload)
    if response.status_code in {200, 201}:
        _created_incident_ids.add(response.json()["id"])
    return response


def test_internal_ingest_auth_validation_camera_dedup_and_persistence():
    payload = incident_payload()
    with TestClient(main.app) as client:
        assert client.post("/api/internal/incidents", json=payload).status_code == 401
        missing_id = {key: value for key, value in payload.items() if key != "event_id"}
        assert post_incident(client, missing_id).status_code == 422
        invalid = post_incident(client, {**payload, "timestamp": "2026-10-16T06:50:00"})
        assert invalid.status_code == 422
        path_traversal = post_incident(client, {**payload, "snapshot_url": "/media/snapshots/../secret.jpg"})
        assert path_traversal.status_code == 422
        unknown_camera = post_incident(client, {**payload, "event_id": f"{payload['event_id']}_unknown", "camera_id": "cam_missing"})
        assert unknown_camera.status_code == 404
        created = post_incident(client, payload)
        duplicate = post_incident(client, payload)
        collision = post_incident(client, {**payload, "confidence": 0.4})
        assert created.status_code == 201, created.text
        assert duplicate.status_code == 200, duplicate.text
        assert collision.status_code == 409
        incident = created.json()
        assert duplicate.json()["id"] == incident["id"]
        assert incident["event_id"] == payload["event_id"]
        assert incident["source"] == "ai_detection"
        assert incident["severity"] == "medium"
        assert incident["severity_verified"] is False
        assert incident["confidence"] == 0.91
        assert incident["workflow_status"] == "not_configured"
        snapshot = client.get("/api/incidents/snapshot").json()
        assert any(item["id"] == incident["id"] for item in snapshot["items"])

    with SessionLocal() as db:
        saved = db.get(Incident, incident["id"])
        assert saved is not None
        assert db.scalar(select(Evidence).where(Evidence.incident_id == incident["id"])) is not None


def test_workflow_callbacks_are_authenticated_idempotent_and_transition_guarded():
    with TestClient(main.app) as client:
        incident = post_incident(client, incident_payload()).json()
        verified = client.patch(
            f"/api/incidents/{incident['id']}",
            headers=DASHBOARD_HEADERS,
            json={"severity": "high"},
        )
        assert verified.status_code == 200
        assert verified.json()["severity_verified"] is True
        assert verified.json()["confidence"] == incident["confidence"]
        url = f"/api/internal/incidents/{incident['id']}/workflow-events"
        notification = {
            "event_id": f"cb_{uuid.uuid4().hex}",
            "type": "notification.sent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        assert client.post(url, json=notification).status_code == 401
        sent = client.post(url, headers=INTERNAL_HEADERS, json=notification)
        assert sent.status_code == 200, sent.text
        assert sent.json()["incident"]["notification_status"] == "sent"
        failure_after_success = client.post(
            url,
            headers=INTERNAL_HEADERS,
            json={**notification, "event_id": f"cb_{uuid.uuid4().hex}", "type": "notification.failed"},
        )
        assert failure_after_success.json()["incident"]["notification_status"] == "sent"

        ack = {
            "event_id": f"cb_{uuid.uuid4().hex}",
            "type": "acknowledgement.received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "responder_id": "operator-7",
        }
        acknowledged = client.post(url, headers=INTERNAL_HEADERS, json=ack)
        assert acknowledged.json()["incident"]["status"] == "acknowledged"
        repeated = client.post(url, headers=INTERNAL_HEADERS, json=ack)
        assert repeated.json()["duplicate"] is True
        rejected_repeat = client.post(
            url,
            headers=INTERNAL_HEADERS,
            json={**ack, "event_id": f"cb_{uuid.uuid4().hex}"},
        )
        assert rejected_repeat.status_code == 409

        escalation = client.post(
            url,
            headers=INTERNAL_HEADERS,
            json={
                "event_id": f"cb_{uuid.uuid4().hex}",
                "type": "escalation.triggered",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert escalation.json()["incident"]["escalated_at"]
        completed = client.post(
            url,
            headers=INTERNAL_HEADERS,
            json={
                "event_id": f"cb_{uuid.uuid4().hex}",
                "type": "workflow.completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert completed.json()["incident"]["status"] == "resolved"
        assert completed.json()["incident"]["resolved_at"]
        assert client.get(f"/api/incidents/{incident['id']}/workflow").json()["workflow_status"] == "completed"


def test_dashboard_acknowledgement_requires_auth_and_prevents_second_ack():
    with TestClient(main.app) as client:
        incident = post_incident(client, incident_payload()).json()
        path = f"/api/incidents/{incident['id']}/acknowledge"
        body = {"event_id": f"ui_{uuid.uuid4().hex}", "responder_id": "operator-1"}
        assert client.post(path, json=body).status_code == 401
        acknowledged = client.post(path, headers=DASHBOARD_HEADERS, json=body)
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["incident"]["responder_id"] == "operator-1"
        repeated = client.post(path, headers=DASHBOARD_HEADERS, json=body)
        assert repeated.json()["duplicate"] is True


def test_websocket_receives_incident_and_workflow_events():
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/incidents") as socket:
            response = post_incident(client, incident_payload())
            assert response.status_code == 201
            created = socket.receive_json()
            workflow = socket.receive_json()
    assert created["event"] == "incident.created"
    assert workflow["event"] == "workflow.updated"
    assert created["data"]["event_id"] == response.json()["event_id"]


def test_n8n_dispatch_and_unavailable_retry_are_persistent(monkeypatch):
    requests_seen = []
    response_code = {"value": 204}
    transport = httpx.MockTransport(
        lambda request: (
            requests_seen.append(request)
            or httpx.Response(response_code["value"], request=request)
        )
    )
    real_client = workflow_service.httpx.AsyncClient
    monkeypatch.setattr(
        workflow_service.httpx,
        "AsyncClient",
        lambda *, timeout: real_client(transport=transport, timeout=timeout),
    )
    monkeypatch.setenv("N8N_ENABLED", "true")
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example.test/webhook/incidents")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "unit-test-only")

    async def dormant_worker(stop):
        await stop.wait()

    monkeypatch.setattr(main, "dispatch_worker", dormant_worker)
    payload = incident_payload()
    with TestClient(main.app) as client:
        incident = post_incident(client, payload).json()

    assert asyncio.run(workflow_service.dispatch_pending_once()) == 1
    request = requests_seen[-1]
    assert request.headers["Idempotency-Key"] == payload["event_id"]
    assert request.headers["X-Webhook-Secret"] == "unit-test-only"
    assert json.loads(request.content)["id"] == incident["id"]
    with SessionLocal() as db:
        outbox = db.scalar(select(WorkflowOutbox).where(WorkflowOutbox.incident_id == incident["id"]))
        assert outbox.status == "sent"
        assert outbox.attempts == 1

    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example.test/webhook/unavailable")
    response_code["value"] = 503
    failed_payload = incident_payload()
    with TestClient(main.app) as client:
        failed_incident = post_incident(client, failed_payload).json()
    assert asyncio.run(workflow_service.dispatch_pending_once()) == 0
    with SessionLocal() as db:
        outbox = db.scalar(select(WorkflowOutbox).where(WorkflowOutbox.incident_id == failed_incident["id"]))
        assert outbox.status == "pending"
        assert outbox.attempts == 1
        assert outbox.last_error
        outbox.next_attempt_at = datetime.now(timezone.utc)
        db.commit()
    assert asyncio.run(workflow_service.dispatch_pending_once()) == 0
    with SessionLocal() as db:
        outbox = db.scalar(select(WorkflowOutbox).where(WorkflowOutbox.incident_id == failed_incident["id"]))
        assert outbox.attempts == 2
        assert outbox.status == "pending"


def test_pending_webhook_is_cancelled_after_acknowledgement(monkeypatch):
    sent_requests = []
    transport = httpx.MockTransport(
        lambda request: sent_requests.append(request) or httpx.Response(204, request=request)
    )
    real_client = workflow_service.httpx.AsyncClient
    monkeypatch.setattr(
        workflow_service.httpx,
        "AsyncClient",
        lambda *, timeout: real_client(transport=transport, timeout=timeout),
    )
    monkeypatch.setenv("N8N_ENABLED", "true")
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example.test/webhook/incidents")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "unit-test-only")

    async def dormant_worker(stop):
        await stop.wait()

    monkeypatch.setattr(main, "dispatch_worker", dormant_worker)
    with TestClient(main.app) as client:
        incident = post_incident(client, incident_payload()).json()
        callback = client.post(
            f"/api/internal/incidents/{incident['id']}/workflow-events",
            headers=INTERNAL_HEADERS,
            json={
                "event_id": f"cb_{uuid.uuid4().hex}",
                "type": "acknowledgement.received",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "responder_id": "operator-3",
            },
        )
        assert callback.status_code == 200

    assert asyncio.run(workflow_service.dispatch_pending_once()) == 0
    assert not sent_requests
    with SessionLocal() as db:
        outbox = db.scalar(select(WorkflowOutbox).where(WorkflowOutbox.incident_id == incident["id"]))
        assert outbox.status == "cancelled"


def test_additive_migration_preserves_existing_rows(tmp_path):
    from sqlalchemy import create_engine, text

    from app.migrations import migrate_database

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE incidents (id VARCHAR(32) PRIMARY KEY, timestamp DATETIME)")
        )
        connection.execute(
            text("INSERT INTO incidents (id, timestamp) VALUES ('inc_legacy', '2026-10-16 06:00:00')")
        )
    migrate_database(legacy_engine)
    with legacy_engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, source, workflow_status FROM incidents WHERE id='inc_legacy'")
        ).one()
    assert row == ("inc_legacy", "simulation", "not_configured")
    legacy_engine.dispose()
