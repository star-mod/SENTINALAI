import json
import logging
import os
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, Evidence, Incident, WorkflowOutbox
from app.schemas import AuthRequest, AuthToken, Camera as CameraSchema
from app.schemas import CameraCreate, CameraUpdate, Evidence as EvidenceSchema
from app.schemas import AcknowledgeRequest, EvidenceCreate, Incident as IncidentSchema
from app.schemas import IncidentCreate, IncidentPatch, InternalIncident, ResolveRequest, SimulateRequest, Stats, WorkflowEvent
from app.services.incident_service import (
    as_contract, camera_or_404, next_incident_id,
    priority_for, validate_transition,
)
from app.services.stream_service import iter_mjpeg
from app.services.video_service import incident_video_url, video_source
from app.services.ws_manager import ws_manager
from app.services.workflow_service import apply_workflow_event, queue_incident, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _token_from_headers(authorization: str | None, alternate: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return alternate or ""


def _configured_token(name: str, demo_default: str) -> str:
    configured = os.getenv(name, "").strip()
    if configured:
        return configured
    if os.getenv("APP_ENV", "development").lower() in {"production", "prod"}:
        raise HTTPException(status_code=503, detail="Required authentication is not configured")
    return demo_default


def require_internal_token(
    authorization: str | None = Header(default=None),
    x_internal_token: str | None = Header(default=None),
) -> None:
    expected = _configured_token("INTERNAL_API_TOKEN", "local-dev-internal-token")
    supplied = _token_from_headers(authorization, x_internal_token)
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid internal API credentials")


def require_dashboard_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = _configured_token("APP_DASHBOARD_TOKEN", "demo-admin-token")
    supplied = _token_from_headers(authorization, None)
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Authentication required")


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
        "created_at": _datetime_iso(row.created_at),
    }


def _datetime_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _ensure_matching_idempotent_event(row: Incident, payload: dict, timestamp: datetime) -> None:
    saved_timestamp = row.timestamp
    if saved_timestamp.tzinfo is None:
        saved_timestamp = saved_timestamp.replace(tzinfo=timezone.utc)
    if (
        row.camera_id != payload["camera_id"]
        or row.type != payload["type"]
        or saved_timestamp.astimezone(timezone.utc) != timestamp.astimezone(timezone.utc)
        or row.confidence != payload["confidence"]
        or row.snapshot_url != payload["snapshot_url"]
        or row.clip_url != payload["clip_url"]
        or row.location != json.dumps(payload["location"])
        or (payload.get("id") is not None and row.id != payload["id"])
    ):
        raise HTTPException(status_code=409, detail="event_id was already used for a different incident payload")


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
    return {"token": _configured_token("APP_DASHBOARD_TOKEN", "demo-admin-token"), "user": {"username": payload.username, "role": "admin"}}


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


@router.get("/incidents/snapshot")
def incident_snapshot(db: Session = Depends(get_db)):
    rows = db.scalars(select(Incident).order_by(Incident.timestamp.desc())).all()
    return {"items": [as_contract(row) for row in rows], "generated_at": datetime.now(timezone.utc).isoformat()}


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
        "severity": body.severity,
        "source": "simulation",
    }
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    await ws_manager.broadcast("workflow.updated", created)
    return created


@router.patch("/incidents/{incident_id}", response_model=IncidentSchema)
async def update_incident(
    incident_id: str,
    body: IncidentPatch,
    db: Session = Depends(get_db),
    _: None = Depends(require_dashboard_token),
):
    row = db.get(Incident, incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        validate_transition(row.status, changes["status"])
        row.status = changes["status"]
        now = utc_now()
        if row.status == "acknowledged":
            row.acknowledged_at = now
            row.workflow_status = "acknowledged"
            row.responder_id = os.getenv("APP_ADMIN_USERNAME", "admin")
            event_type = "acknowledgement.received"
        elif row.status == "resolved":
            row.resolved_at = now
            row.workflow_status = "completed"
            event_type = "workflow.completed"
        row.workflow_updated_at = now
        row.updated_at = now
        db.add(WorkflowAudit(
            event_id=f"dashboard_{uuid.uuid4().hex}",
            incident_id=incident_id,
            event_type=event_type,
            payload=json.dumps({"status": row.status, "responder_id": row.responder_id}),
            created_at=now,
        ))
    if "notes" in changes and changes["notes"] is not None:
        row.notes = changes["notes"]
        row.updated_at = utc_now()
    if "severity" in changes and changes["severity"] is not None:
        row.severity = changes["severity"]
        row.severity_verified = True
        row.priority = priority_for(row.confidence, row.severity)
        now = utc_now()
        row.updated_at = now
        db.add(WorkflowAudit(
            event_id=f"dashboard_{uuid.uuid4().hex}",
            incident_id=incident_id,
            event_type="severity.verified",
            payload=json.dumps({"severity": row.severity}),
            created_at=now,
        ))
    db.commit()
    db.refresh(row)
    result = as_contract(row)
    await ws_manager.broadcast("incident.updated", result)
    await ws_manager.broadcast("workflow.updated", result)
    return result


@router.get("/incidents/{incident_id}/workflow")
def incident_workflow(incident_id: str, db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    dispatches = db.scalars(
        select(WorkflowOutbox)
        .where(WorkflowOutbox.incident_id == incident_id)
        .order_by(WorkflowOutbox.created_at.desc())
    ).all()
    return {
        "incident_id": incident_id,
        "workflow_status": incident.workflow_status,
        "workflow_updated_at": _datetime_iso(incident.workflow_updated_at),
        "notification_status": incident.notification_status,
        "notification_attempts": incident.notification_attempts,
        "notification_sent_at": _datetime_iso(incident.notification_sent_at),
        "acknowledged_at": _datetime_iso(incident.acknowledged_at),
        "escalated_at": _datetime_iso(incident.escalated_at),
        "resolved_at": _datetime_iso(incident.resolved_at),
        "responder_id": incident.responder_id,
        "dispatches": [
            {
                "status": dispatch.status,
                "attempts": dispatch.attempts,
                "next_attempt_at": _datetime_iso(dispatch.next_attempt_at),
                "last_error": dispatch.last_error,
            }
            for dispatch in dispatches
        ],
    }


async def _apply_and_broadcast_workflow_event(db: Session, incident_id: str, event: WorkflowEvent) -> dict:
    try:
        incident, duplicate = apply_workflow_event(db, incident_id, event)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    contract = as_contract(incident)
    if not duplicate:
        await ws_manager.broadcast("incident.updated", contract)
        await ws_manager.broadcast("workflow.updated", contract)
    return {"incident": contract, "duplicate": duplicate}


@router.post("/internal/incidents/{incident_id}/workflow-events")
async def workflow_event_callback(
    incident_id: str,
    body: WorkflowEvent,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    return await _apply_and_broadcast_workflow_event(db, incident_id, body)


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: str,
    body: AcknowledgeRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_dashboard_token),
):
    event = WorkflowEvent(
        event_id=body.event_id,
        type="acknowledgement.received",
        timestamp=utc_now(),
        responder_id=body.responder_id,
    )
    return await _apply_and_broadcast_workflow_event(db, incident_id, event)


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    body: ResolveRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_dashboard_token),
):
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if body.notes:
        incident.notes = body.notes
    event = WorkflowEvent(
        event_id=body.event_id,
        type="workflow.completed",
        timestamp=utc_now(),
    )
    return await _apply_and_broadcast_workflow_event(db, incident_id, event)


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
    timestamp = payload["timestamp"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise HTTPException(status_code=422, detail="timestamp must include an ISO 8601 timezone")
    event_id = payload["event_id"]
    existing = db.scalar(select(Incident).where(Incident.event_id == event_id))
    if existing is not None:
        _ensure_matching_idempotent_event(existing, payload, timestamp)
        return as_contract(existing)
    incident_id = payload.get("id") or next_incident_id(db)
    if db.get(Incident, incident_id) is not None:
        raise HTTPException(status_code=409, detail="Incident ID already exists")
    now = utc_now()
    severity = payload.get("severity") or "medium"
    row = Incident(
        id=incident_id,
        schema_version=payload.get("schema_version", "1.0"),
        event_id=event_id,
        camera_id=payload["camera_id"],
        camera_name=payload["camera_name"],
        location=json.dumps(payload["location"]),
        type=payload["type"],
        confidence=payload["confidence"],
        severity=severity,
        severity_verified=False,
        priority=payload.get("priority") or priority_for(payload["confidence"], severity),
        timestamp=timestamp,
        status="new",
        snapshot_url=payload["snapshot_url"],
        clip_url=payload["clip_url"],
        notes=payload.get("notes", ""),
        verification=json.dumps(payload["verification"] or {"window_seconds": 2.5, "frames_confirmed": 30, "frames_required": 25}),
        source=payload.get("source", "simulation"),
        workflow_status="queued" if os.getenv("N8N_ENABLED", "false").lower() == "true" else "not_configured",
        notification_status="pending" if os.getenv("N8N_ENABLED", "false").lower() == "true" else "not_configured",
        workflow_updated_at=now,
        detection_metadata=json.dumps(payload.get("detection_metadata", {})),
        updated_at=now,
    )
    db.add(row)
    db.flush()
    snapshot = Evidence(
        id=f"ev_{uuid.uuid4().hex[:24]}",
        incident_id=incident_id,
        type="snapshot",
        url=payload["snapshot_url"],
        created_at=now,
    )
    db.add(snapshot)
    if payload["clip_url"].startswith("/media/clips/"):
        db.add(Evidence(
            id=f"ev_{uuid.uuid4().hex[:24]}",
            incident_id=incident_id,
            type="clip",
            url=payload["clip_url"],
            created_at=now,
        ))
    event = as_contract(row)
    queue_incident(db, event)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        duplicate = db.scalar(select(Incident).where(Incident.event_id == event_id))
        if duplicate is not None:
            _ensure_matching_idempotent_event(duplicate, payload, timestamp)
            return as_contract(duplicate)
        raise HTTPException(status_code=409, detail="Incident could not be stored due to a conflicting ID") from error
    db.refresh(row)
    return as_contract(row)


@router.post("/internal/incidents", response_model=IncidentSchema, status_code=201)
async def create_internal_incident(
    body: InternalIncident,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    payload = body.model_dump(exclude_none=True)
    camera = camera_or_404(db, payload["camera_id"])
    payload["camera_name"] = body.camera_name or camera.name
    payload["location"] = body.location.model_dump() if body.location is not None else json.loads(camera.location)
    payload["verification"] = (body.verification.model_dump() if body.verification is not None else {"window_seconds": 2.5, "frames_confirmed": 30, "frames_required": 25})
    payload["severity"] = body.severity or "medium"
    payload["timestamp"] = body.timestamp
    payload["event_id"] = body.event_id
    existing = db.scalar(select(Incident).where(Incident.event_id == payload["event_id"]))
    if existing is not None:
        _ensure_matching_idempotent_event(existing, payload, body.timestamp)
        response.status_code = 200
        return as_contract(existing)
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    await ws_manager.broadcast("workflow.updated", created)
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
        "source": "simulation",
        "event_id": f"evt_{uuid.uuid4().hex}",
    }
    created = _create_incident(db, payload)
    await ws_manager.broadcast("incident.created", created)
    await ws_manager.broadcast("workflow.updated", created)
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