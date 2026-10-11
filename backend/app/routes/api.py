import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, Evidence, Incident, User
from app.schemas import AuthRequest, AuthToken, Camera as CameraSchema
from app.schemas import CameraCreate, CameraUpdate, Evidence as EvidenceSchema
from app.schemas import EvidenceCreate, Incident as IncidentSchema
from app.schemas import IncidentCreate, IncidentPatch, InternalIncident, SimulateRequest, Stats
from app.seed import CAMERAS
from app.services.incident_service import as_contract, camera_or_404, next_incident_id, severity_for, validate_transition
from app.services.stream_service import iter_mjpeg
from app.services.video_service import incident_video_url, video_source
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _camera_to_contract(camera: Camera) -> dict:
    return {
        "id": camera.id,
        "name": camera.name,
        "location": json.loads(camera.location),
        "status": camera.status,
        "stream_url": camera.stream_url,
    }


def _evidence_to_contract(row: Evidence) -> dict:
    return {
        "id": row.id,
        "incident_id": row.incident_id,
        "type": row.type,
        "url": row.url,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    cameras = db.scalars(select(Camera)).all()
    return {"status": "ok", "service": "SentinelAI Control API", "cameras_online": sum(cam.status == "online" for cam in cameras), "cameras_total": len(cameras), "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/auth/login", response_model=AuthToken)
def login(payload: AuthRequest):
    expected_user = os.getenv("APP_ADMIN_USERNAME", "admin")
    expected_password = os.getenv("APP_ADMIN_PASSWORD", "admin123")
    if payload.username != expected_user or payload.password != expected_password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": "demo-admin-token", "user": {"username": payload.username, "role": "admin"}}


@router.get("/auth/me")
def me():
    return {"username": os.getenv("APP_ADMIN_USERNAME", "admin"), "role": "admin"}


@router.get("/cameras", response_model=list[CameraSchema])
def cameras(db: Session = Depends(get_db)):
    return [_camera_to_contract(cam) for cam in db.scalars(select(Camera).order_by(Camera.id)).all()]


@router.get("/cameras/{camera_id}", response_model=CameraSchema)
def camera_detail(camera_id: str, db: Session = Depends(get_db)):
    camera = camera_or_404(db, camera_id)
    return _camera_to_contract(camera)


@router.post("/cameras", response_model=CameraSchema, status_code=201)
def create_camera(body: CameraCreate, db: Session = Depends(get_db)):
    camera_id = body.id or f"cam_{uuid.uuid4().hex[:8]}"
    if db.get(Camera, camera_id) is not None:
        raise HTTPException(status_code=409, detail="Camera already exists")
    row = Camera(
        id=camera_id,
        name=body.name,
        location=json.dumps(body.location.model_dump()),
        status=body.status,
        stream_url=body.stream_url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _camera_to_contract(row)


@router.patch("/cameras/{camera_id}", response_model=CameraSchema)
def update_camera(camera_id: str, body: CameraUpdate, db: Session = Depends(get_db)):
    camera = camera_or_404(db, camera_id)
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        camera.name = updates["name"]
    if "location" in updates and updates["location"] is not None:
        camera.location = json.dumps(updates["location"].model_dump())
    if "status" in updates and updates["status"] is not None:
        camera.status = updates["status"]
    if "stream_url" in updates and updates["stream_url"] is not None:
        camera.stream_url = updates["stream_url"]
    db.commit(); db.refresh(camera)
    return _camera_to_contract(camera)


@router.delete("/cameras/{camera_id}", status_code=204)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = camera_or_404(db, camera_id)
    db.delete(camera)
    db.commit()
    return None


@router.get("/incidents", response_model=list[IncidentSchema])
def incidents(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    camera_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = select(Incident)
    if status:
        query = query.where(Incident.status == status)
    if type:
        query = query.where(Incident.type == type)
    if camera_id:
        query = query.where(Incident.camera_id == camera_id)
    return [as_contract(row) for row in db.scalars(query.order_by(Incident.timestamp.desc())).all()]


@router.get("/incidents/{incident_id}", response_model=IncidentSchema)
def incident_detail(incident_id: str, db: Session = Depends(get_db)):
    row = db.get(Incident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return as_contract(row)


@router.post("/incidents", response_model=IncidentSchema, status_code=201)
async def create_incident(body: IncidentCreate, db: Session = Depends(get_db)):
    camera = camera_or_404(db, body.camera_id)
    payload = {
        "camera_id": body.camera_id,
        "camera_name": body.camera_name or camera.name,
        "location": (body.location.model_dump() if body.location else json.loads(camera.location)),
        "type": body.type,
        "confidence": body.confidence,
        "timestamp": body.timestamp or datetime.now(timezone.utc).isoformat(),
        "snapshot_url": body.snapshot_url,
        "clip_url": body.clip_url,
        "notes": body.notes,
        "verification": (body.verification.model_dump() if body.verification else {"window_seconds": 2.5, "frames_confirmed": 30, "frames_required": 25}),
    }
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    return created


@router.patch("/incidents/{incident_id}", response_model=IncidentSchema)
async def update_incident(incident_id: str, body: IncidentPatch, db: Session = Depends(get_db)):
    row = db.get(Incident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        validate_transition(row.status, changes["status"])
        row.status = changes["status"]
    if "notes" in changes and changes["notes"] is not None:
        row.notes = changes["notes"]
    db.commit()
    db.refresh(row)
    result = as_contract(row)
    await ws_manager.broadcast("incident.updated", result)
    return result


@router.get("/stats", response_model=Stats)
def stats(db: Session = Depends(get_db)):
    rows = db.scalars(select(Incident)).all()
    cameras_rows = db.scalars(select(Camera).order_by(Camera.id)).all()
    now = datetime.now(timezone.utc)
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    by_hour = {(start + timedelta(hours=index)).strftime("%H:00"): 0 for index in range(24)}
    by_type = {key: 0 for key in ("physical_altercation", "fall_collapse", "abnormal_crowd_movement")}
    by_status = {key: 0 for key in ("new", "acknowledged", "resolved")}
    by_camera = {cam.id: {"camera_id": cam.id, "name": cam.name, "count": 0} for cam in cameras_rows}
    for row in rows:
        by_type[row.type] = by_type.get(row.type, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
        if row.camera_id in by_camera:
            by_camera[row.camera_id]["count"] += 1
        stamp = row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=timezone.utc)
        if stamp >= start:
            by_hour[stamp.astimezone(timezone.utc).strftime("%H:00")] += 1
    return {"total": len(rows), "by_type": by_type, "by_status": by_status, "by_hour": [{"hour": hour, "count": count} for hour, count in by_hour.items()], "by_camera": sorted(by_camera.values(), key=lambda item: item["count"], reverse=True)}


def _create_incident(db: Session, payload: dict) -> dict:
    incident_id = next_incident_id(db)
    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    row = Incident(
        id=incident_id,
        camera_id=payload["camera_id"],
        camera_name=payload["camera_name"],
        location=json.dumps(payload["location"]),
        type=payload["type"],
        confidence=payload["confidence"],
        severity=payload.get("severity") or severity_for(payload["confidence"]),
        timestamp=timestamp,
        status="new",
        snapshot_url=payload["snapshot_url"],
        clip_url=payload["clip_url"],
        notes=payload.get("notes", ""),
        verification=json.dumps(payload["verification"] or {"window_seconds": 2.5, "frames_confirmed": 30, "frames_required": 25}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return as_contract(row)


@router.post("/internal/incidents", response_model=IncidentSchema, status_code=201)
async def create_internal_incident(body: InternalIncident, db: Session = Depends(get_db)):
    payload = body.model_dump(exclude_none=True)
    camera = camera_or_404(db, payload["camera_id"])
    payload["camera_name"] = body.camera_name or camera.name
    payload["location"] = body.location.model_dump() if body.location is not None else json.loads(camera.location)
    payload["verification"] = (body.verification.model_dump() if body.verification is not None else {"window_seconds": 2.5, "frames_confirmed": 30, "frames_required": 25})
    payload["severity"] = body.severity or severity_for(body.confidence)
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    return created


@router.post("/simulate", response_model=IncidentSchema, status_code=201)
async def simulate(body: SimulateRequest, db: Session = Depends(get_db)):
    camera = camera_or_404(db, body.camera_id)
    location = json.loads(camera.location)
    confidence = round(random.uniform(0.78, 0.97), 2)
    slug = body.type
    payload = {
        "camera_id": camera.id,
        "camera_name": camera.name,
        "location": location,
        "type": body.type,
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot_url": f"/media/snapshots/{camera.id}_{slug}.jpg",
        "clip_url": incident_video_url(slug),
        "notes": "Simulated demo drill for human operator review.",
        "verification": {"window_seconds": 2.5, "frames_confirmed": random.randint(30, 44), "frames_required": 25},
    }
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    return created


@router.post("/evidence/upload", response_model=EvidenceSchema, status_code=201)
def upload_evidence(body: EvidenceCreate, db: Session = Depends(get_db)):
    incident = db.get(Incident, body.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    row = Evidence(
        id=f"ev_{uuid.uuid4().hex[:8]}",
        incident_id=body.incident_id,
        type=body.type,
        url=body.url,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit(); db.refresh(row)
    return _evidence_to_contract(row)


@router.get("/evidence/{evidence_id}", response_model=EvidenceSchema)
def detail_evidence(evidence_id: str, db: Session = Depends(get_db)):
    row = db.get(Evidence, evidence_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return _evidence_to_contract(row)


@router.get("/incidents/{incident_id}/evidence", response_model=list[EvidenceSchema])
def incident_evidence(incident_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.created_at.desc())).all()
    return [_evidence_to_contract(row) for row in rows]


@router.get("/stream/{camera_id}")
def camera_stream(camera_id: str, db: Session = Depends(get_db)):
    camera = camera_or_404(db, camera_id)
    video = video_source(camera_id)
    video_path = str(video) if video else None
    return StreamingResponse(iter_mjpeg(camera_id, video_path), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@router.get("/incident-video/{incident_type}")
def incident_video(incident_type: str):
    camera_id = {"fall_collapse": "cam_01", "physical_altercation": "cam_02", "abnormal_crowd_movement": "cam_03"}.get(incident_type)
    if camera_id is None:
        raise HTTPException(status_code=404, detail="Incident video not found")
    video = video_source(camera_id)
    if video is None:
        raise HTTPException(status_code=404, detail="No footage is available for this incident type")
    return FileResponse(video, media_type="video/mp4")