import json
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Camera, Incident
from app.services.video_service import resolve_incident_clip


def severity_for(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.70:
        return "medium"
    return "low"


def as_contract(row: Incident) -> dict:
    timestamp = row.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "id": row.id, "camera_id": row.camera_id, "camera_name": row.camera_name,
        "location": json.loads(row.location), "type": row.type,
        "confidence": row.confidence, "severity": row.severity,
        "timestamp": timestamp.isoformat(), "status": row.status,
        "snapshot_url": row.snapshot_url,
        "clip_url": resolve_incident_clip(row.camera_id, row.type, row.clip_url),
        "notes": row.notes,
        "verification": json.loads(row.verification),
    }


def next_incident_id(db: Session) -> str:
    rows = db.scalars(select(Incident.id)).all()
    latest = max((int(value[4:]) for value in rows if value.startswith("inc_")), default=0)
    return f"inc_{latest + 1:04d}"


def camera_or_404(db: Session, camera_id: str) -> Camera:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def validate_transition(current: str, target: str) -> None:
    allowed = {"new": {"new", "acknowledged"}, "acknowledged": {"acknowledged", "resolved"}, "resolved": {"resolved"}}
    if target not in allowed[current]:
        raise HTTPException(status_code=409, detail=f"Invalid status transition: {current} -> {target}")