import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Incident as IncidentModel
from app.services.incident_service import severity_for, validate_transition


@pytest.mark.parametrize(("confidence", "expected"), [(0.69, "low"), (0.70, "medium"), (0.84, "medium"), (0.85, "high")])
def test_severity_thresholds(confidence, expected):
    assert severity_for(confidence) == expected


def test_status_transitions_are_forward_only():
    validate_transition("new", "acknowledged")
    validate_transition("acknowledged", "resolved")
    with pytest.raises(HTTPException) as error:
        validate_transition("new", "resolved")
    assert error.value.status_code == 409


def test_simulate_creates_contract_incident():
    with TestClient(app) as client:
        response = client.post("/api/simulate", json={"type": "fall_collapse", "camera_id": "cam_01"})
        incident = response.json()
        acknowledged = client.patch(f"/api/incidents/{incident['id']}", json={"status": "acknowledged"})
        resolved = client.patch(f"/api/incidents/{incident['id']}", json={"status": "resolved", "notes": "Reviewed by operator"})
        invalid = client.patch(f"/api/incidents/{incident['id']}", json={"status": "new"})
    assert response.status_code == 201
    assert incident["camera_id"] == "cam_01"
    assert incident["type"] == "fall_collapse"
    assert incident["status"] == "new"
    assert incident["severity"] in {"low", "medium", "high"}
    assert incident["clip_url"] == "/api/incident-video/fall_collapse"
    assert acknowledged.json()["status"] == "acknowledged"
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["notes"] == "Reviewed by operator"
    assert invalid.status_code == 409
    with SessionLocal() as db:
        created_row = db.get(IncidentModel, incident["id"])
        if created_row is not None:
            db.delete(created_row)
            db.commit()


def test_incident_video_serves_matching_mp4():
    with TestClient(app) as client:
        response = client.get("/api/incident-video/fall_collapse")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    assert len(response.content) > 100_000


def test_camera_crud_round_trip():
    with TestClient(app) as client:
        create_response = client.post("/api/cameras", json={
            "id": "cam_live_101",
            "name": "Loading Bay",
            "location": {"lat": 12.9, "lng": 77.6, "label": "Loading Bay"},
            "status": "online",
            "stream_url": "/api/stream/cam_live_101"
        })
        assert create_response.status_code == 201, create_response.text
        payload = create_response.json()
        assert payload["id"] == "cam_live_101"

        list_response = client.get("/api/cameras")
        assert list_response.status_code == 200
        assert any(camera["id"] == "cam_live_101" for camera in list_response.json())

        patch_response = client.patch("/api/cameras/cam_live_101", json={"status": "offline"})
        assert patch_response.status_code == 200
        assert patch_response.json()["status"] == "offline"

        delete_response = client.delete("/api/cameras/cam_live_101")
        assert delete_response.status_code == 204


def test_ai_ingest_creates_incident_and_evidence():
    with TestClient(app) as client:
        response = client.post("/api/internal/incidents", json={
            "camera_id": "cam_01",
            "camera_name": "Central Plaza - North",
            "location": {"lat": 12.9716, "lng": 77.5946, "label": "Central Plaza"},
            "type": "fall_collapse",
            "confidence": 0.93,
            "severity": "high",
            "timestamp": "2026-10-11T12:00:00Z",
            "snapshot_url": "/media/snapshots/ingest.jpg",
            "clip_url": "/api/incident-video/fall_collapse",
            "notes": "AI ingest validation",
            "verification": {"window_seconds": 2.5, "frames_confirmed": 40, "frames_required": 25}
        })
        assert response.status_code == 201, response.text
        incident = response.json()
        assert incident["camera_id"] == "cam_01"
        assert incident["type"] == "fall_collapse"

        evidence_response = client.post("/api/evidence/upload", json={
            "incident_id": incident["id"],
            "type": "snapshot",
            "url": "/media/snapshots/ingest.jpg"
        })
        assert evidence_response.status_code == 201, evidence_response.text
        evidence = evidence_response.json()
        assert evidence["incident_id"] == incident["id"]

        list_response = client.get(f"/api/incidents/{incident['id']}/evidence")
        assert list_response.status_code == 200
        assert any(item["id"] == evidence["id"] for item in list_response.json())