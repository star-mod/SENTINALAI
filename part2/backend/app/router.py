"""FastAPI REST & Streaming Router for SentinelAI.
Implements the exact Shared Contract specifications.
"""

import asyncio
import os
import random
import time
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from backend.app.database import db
from backend.app.schemas import (
    Incident,
    Camera,
    IncidentPatchRequest,
    SimulateRequest,
    InternalIncidentCreate,
    StatsResponse,
)
from backend.app.websocket import ws_manager
from sentinel_ai.frame_hub import FrameHub

api_router = APIRouter()


@api_router.get("/health")
def get_health():
    """System health check and operational status."""
    cameras = db.get_cameras()
    online_count = sum(1 for c in cameras if c.status == "online")
    return {
        "status": "ok",
        "service": "SentinelAI Control API",
        "cameras_online": online_count,
        "cameras_total": len(cameras),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/cameras", response_model=List[Camera])
def get_cameras():
    """Lists authorized CCTV camera feeds."""
    return db.get_cameras()


@api_router.get("/incidents", response_model=List[Incident])
def get_incidents(
    status: Optional[str] = Query(None, description="Filter by status: new, acknowledged, resolved"),
    type: Optional[str] = Query(None, description="Filter by type"),
    camera_id: Optional[str] = Query(None, description="Filter by camera_id"),
):
    """Retrieves safety incidents (newest first)."""
    return db.get_incidents(status=status, type_=type, camera_id=camera_id)


@api_router.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: str):
    """Retrieves full details for a single incident."""
    inc = db.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


@api_router.patch("/incidents/{incident_id}", response_model=Incident)
async def patch_incident(incident_id: str, body: IncidentPatchRequest):
    """Updates incident status (acknowledged/resolved) and operator notes (optimistic UI)."""
    updated = db.update_incident(incident_id, status=body.status, notes=body.notes)
    if not updated:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Broadcast event to all WebSocket clients
    await ws_manager.broadcast_event("incident.updated", updated)
    return updated


@api_router.get("/stats", response_model=StatsResponse)
def get_stats():
    """Aggregates analytics: distribution by type, status, hour, and camera hotspots."""
    return db.get_stats()


@api_router.post("/simulate", response_model=Incident)
async def simulate_incident(body: SimulateRequest):
    """Fires a deterministic incident for hackathon demo fallback and testing."""
    cam = db.get_camera(body.camera_id)
    if not cam:
        cam = db.get_cameras()[0]

    confidence = round(random.uniform(0.86, 0.96), 2)
    severity = "high" if confidence >= 0.85 else ("medium" if confidence >= 0.70 else "low")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Pre-select matching clip/snapshot fallback
    clip_map = {
        "fall_collapse": "/media/clips/cam_01_fall.mp4",
        "physical_altercation": "/media/clips/cam_02_altercation.mp4",
        "abnormal_crowd_movement": "/media/clips/cam_03_crowd.mp4",
        "vehicle_accident": "/media/clips/cam_04_accident.mp4",
    }
    snapshot_map = {
        "fall_collapse": "/media/snapshots/cam_01_fall.jpg",
        "physical_altercation": "/media/snapshots/cam_02_altercation.jpg",
        "abnormal_crowd_movement": "/media/snapshots/cam_03_crowd.jpg",
        "vehicle_accident": "/media/snapshots/cam_04_accident.jpg",
    }

    simulated_data = {
        "camera_id": cam.id,
        "camera_name": cam.name,
        "location": cam.location,
        "type": body.type,
        "confidence": confidence,
        "severity": severity,
        "timestamp": now_iso,
        "status": "new",
        "snapshot_url": snapshot_map.get(body.type, "/media/snapshots/inc_simulated.jpg"),
        "clip_url": clip_map.get(body.type, "/media/clips/inc_simulated.mp4"),
        "notes": f"Simulated demo drill: {body.type.replace('_', ' ').capitalize()} triggered via Demo Mode.",
        "verification": {
            "window_seconds": 2.5,
            "frames_confirmed": int(random.randint(32, 44)),
            "frames_required": 25,
        },
    }

    created = db.create_incident(simulated_data)
    await ws_manager.broadcast_event("incident.created", created)
    return created


@api_router.post("/internal/incidents", response_model=Incident)
async def create_internal_incident(body: InternalIncidentCreate):
    """Internal ingress endpoint called by SentinelAI CV pipeline upon verified incident."""
    created = db.create_incident(body.model_dump())
    await ws_manager.broadcast_event("incident.created", created)
    return created


@api_router.get("/stream/{camera_id}")
def stream_camera(camera_id: str):
    """MJPEG live streaming endpoint with bounding box & pose overlay."""
    def frame_generator():
        while True:
            jpeg_bytes = FrameHub.get_latest_jpeg(camera_id)
            if jpeg_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
                )
            time.sleep(0.066)  # ~15 FPS

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
