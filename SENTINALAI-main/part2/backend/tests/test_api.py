"""Automated API Test Suite for SentinelAI Backend.
Validates all endpoints specified in the Shared Contract.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

# Create test client without starting background workers during unit test
client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "cameras_online" in data


def test_cameras():
    response = client.get("/api/cameras")
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) >= 4
    for cam in cameras:
        assert "id" in cam
        assert "name" in cam
        assert "location" in cam
        assert "status" in cam
        assert "stream_url" in cam


def test_incidents_crud_and_patch():
    # 1. Fetch all
    response = client.get("/api/incidents")
    assert response.status_code == 200
    incidents = response.json()
    assert len(incidents) >= 1

    first_inc = incidents[0]
    inc_id = first_inc["id"]

    # 2. Fetch single
    res_single = client.get(f"/api/incidents/{inc_id}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == inc_id

    # 3. Patch status to 'acknowledged' and add notes
    patch_payload = {
        "status": "acknowledged",
        "notes": "Unit test verified incident"
    }
    res_patch = client.patch(f"/api/incidents/{inc_id}", json=patch_payload)
    assert res_patch.status_code == 200
    patched_data = res_patch.json()
    assert patched_data["status"] == "acknowledged"
    assert patched_data["notes"] == "Unit test verified incident"


def test_stats():
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "by_type" in data
    assert "by_status" in data
    assert "by_hour" in data
    assert "by_camera" in data


def test_simulate():
    payload = {
        "type": "physical_altercation",
        "camera_id": "cam_02"
    }
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    created = response.json()
    assert created["camera_id"] == "cam_02"
    assert created["type"] == "physical_altercation"
    assert created["status"] == "new"
    assert created["confidence"] >= 0.70
    assert "verification" in created


def test_internal_incident_create():
    payload = {
        "camera_id": "cam_01",
        "camera_name": "Central Plaza - North",
        "location": {"lat": 12.9716, "lng": 77.5946, "label": "Central Plaza"},
        "type": "fall_collapse",
        "confidence": 0.94,
        "severity": "high",
        "timestamp": "2026-10-09T18:00:00Z",
        "snapshot_url": "/media/snapshots/test.jpg",
        "clip_url": "/media/clips/test.mp4",
        "notes": "Automated internal test trigger",
        "verification": {"window_seconds": 2.5, "frames_confirmed": 36, "frames_required": 25}
    }
    response = client.post("/api/internal/incidents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "fall_collapse"
    assert data["severity"] == "high"
