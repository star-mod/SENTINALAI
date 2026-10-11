import json
import logging
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, Incident
from app.schemas import Camera as CameraSchema
from app.schemas import Incident as IncidentSchema
from app.schemas import IncidentPatch, InternalIncident, SimulateRequest, Stats
from app.seed import CAMERAS
from app.services.incident_service import as_contract, camera_or_404, next_incident_id, severity_for, validate_transition
from app.services.stream_service import iter_mjpeg
from app.services.video_service import incident_video_url, video_source
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
def health(db: Session = Depends(get_db)):
    cameras = db.scalars(select(Camera)).all()
    return {"status": "ok", "service": "SentinelAI Control API", "cameras_online": sum(cam.status == "online" for cam in cameras), "cameras_total": len(cameras), "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/cameras", response_model=list[CameraSchema])
def cameras(db: Session = Depends(get_db)):
    return [{"id": cam.id, "name": cam.name, "location": json.loads(cam.location), "status": cam.status, "stream_url": cam.stream_url} for cam in db.scalars(select(Camera).order_by(Camera.id)).all()]


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
    by_hour = { (start + timedelta(hours=index)).strftime("%H:00"): 0 for index in range(24) }
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
        id=incident_id, camera_id=payload["camera_id"], camera_name=payload["camera_name"],
        location=json.dumps(payload["location"]), type=payload["type"], confidence=payload["confidence"],
        severity=severity_for(payload["confidence"]), timestamp=timestamp,
        status="new", snapshot_url=payload["snapshot_url"], clip_url=payload["clip_url"],
        notes=payload.get("notes", ""), verification=json.dumps(payload["verification"]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return as_contract(row)


@router.post("/internal/incidents", response_model=IncidentSchema, status_code=201)
async def create_internal_incident(body: InternalIncident, db: Session = Depends(get_db)):
    payload = body.model_dump()
    camera_or_404(db, payload["camera_id"])
    payload["location"] = body.location.model_dump()
    payload["verification"] = body.verification.model_dump()
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
        "camera_id": camera.id, "camera_name": camera.name, "location": location,
        "type": body.type, "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot_url": f"/media/snapshots/{camera.id}_{slug}.jpg",
        "clip_url": incident_video_url(slug),
        "notes": "Simulated demo drill for human operator review.",
        "verification": {"window_seconds": 2.5, "frames_confirmed": random.randint(30, 44), "frames_required": 25},
    }
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    return created


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