import hashlib
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
        "severity_verified": row.severity_verified,
        "timestamp": timestamp.isoformat(), "status": row.status,
        "snapshot_url": row.snapshot_url,
        "clip_url": resolve_incident_clip(row.camera_id, row.type, row.clip_url),
        "notes": row.notes,
        "verification": json.loads(row.verification),
        "schema_version": row.schema_version or "1.0",
        "event_id": row.event_id,
        "source": row.source or "simulation",
        "priority": row.priority or "normal",
        "workflow_status": row.workflow_status or "not_configured",
        "workflow_updated_at": _iso(row.workflow_updated_at),
        "notification_status": row.notification_status or "not_configured",
        "notification_attempts": row.notification_attempts or 0,
        "notification_sent_at": _iso(row.notification_sent_at),
        "acknowledged_at": _iso(row.acknowledged_at),
        "escalated_at": _iso(row.escalated_at),
        "resolved_at": _iso(row.resolved_at),
        "responder_id": row.responder_id,
        "detection_metadata": json.loads(row.detection_metadata or "{}"),
        "updated_at": _iso(row.updated_at),
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def event_fingerprint(camera_id: str, incident_type: str, timestamp: str) -> str:
    raw = f"{camera_id}:{incident_type}:{timestamp}".encode("utf-8")
    return f"evt_{hashlib.sha256(raw).hexdigest()}"


def priority_for(confidence: float, severity: str) -> str:
    if confidence < 0.6:
        return "uncertain"
    if severity == "high" or confidence >= 0.85:
        return "high"
    if severity == "medium" or confidence >= 0.7:
        return "medium"
    return "normal"


def next_incident_id(db: Session) -> str:
    rows = db.scalars(select(Incident.id)).all()
    numeric_ids = (
        int(value[4:])
        for value in rows
        if value.startswith("inc_") and value[4:].isdigit()
    )
    latest = max(numeric_ids, default=0)
    return f"inc_{latest + 1:04d}"


def camera_or_404(db: Session, camera_id: str) -> Camera:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def validate_transition(current: str, target: str) -> None:
    allowed = {"new": {"acknowledged"}, "acknowledged": {"resolved"}, "resolved": set()}
    if target not in allowed[current]:
        raise HTTPException(status_code=409, detail=f"Invalid status transition: {current} -> {target}")