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