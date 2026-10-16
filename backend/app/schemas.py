from datetime import datetime
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


IncidentType = Literal["physical_altercation", "fall_collapse", "abnormal_crowd_movement"]
IncidentStatus = Literal["new", "acknowledged", "resolved"]
Severity = Literal["low", "medium", "high"]
Priority = Literal["high", "medium", "uncertain", "normal"]


def _timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include an ISO 8601 timezone")
    return value


def _evidence_url(value: str, *, allow_clip: bool = False) -> str:
    parts = urlsplit(value)
    safe_snapshot = re.fullmatch(r"/media/snapshots/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)", value)
    safe_clip = re.fullmatch(r"/media/clips/[A-Za-z0-9_-]+\.mp4", value)
    safe_video = re.fullmatch(
        r"/api/incident-video/(?:physical_altercation|fall_collapse|abnormal_crowd_movement)",
        value,
    )
    accepted = bool(safe_snapshot or (allow_clip and (safe_clip or safe_video)))
    if parts.scheme or parts.netloc or not accepted or parts.query or parts.fragment:
        raise ValueError("evidence URL must be a safe application media URL")
    return value


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    label: str = Field(min_length=1, max_length=200)


class Verification(BaseModel):
    window_seconds: float = Field(default=2.5, gt=0, le=600)
    frames_confirmed: int = Field(default=30, ge=0)
    frames_required: int = Field(default=25, ge=1)


class Incident(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_id: str
    camera_name: str
    location: Location
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity
    severity_verified: bool = False
    timestamp: datetime
    status: IncidentStatus
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification
    schema_version: str = "1.0"
    event_id: str | None = None
    source: Literal["ai_detection", "simulation"] = "simulation"
    priority: Priority = "normal"
    workflow_status: str = "not_configured"
    workflow_updated_at: datetime | None = None
    notification_status: Literal["pending", "sent", "failed", "not_configured"] = "not_configured"
    notification_attempts: int = 0
    notification_sent_at: datetime | None = None
    acknowledged_at: datetime | None = None
    escalated_at: datetime | None = None
    resolved_at: datetime | None = None
    responder_id: str | None = None
    detection_metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        return _timezone_aware(value)


class Camera(BaseModel):
    id: str
    name: str
    location: Location
    status: Literal["online", "offline"]
    stream_url: str


class CameraCreate(BaseModel):
    id: str | None = None
    name: str
    location: Location
    status: Literal["online", "offline"] = "online"
    stream_url: str


class CameraUpdate(BaseModel):
    name: str | None = None
    location: Location | None = None
    status: Literal["online", "offline"] | None = None
    stream_url: str | None = None


class IncidentPatch(BaseModel):
    status: IncidentStatus | None = None
    notes: str | None = None
    severity: Severity | None = None


class InternalIncident(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    camera_id: str = Field(min_length=1, max_length=32)
    camera_name: str | None = Field(default=None, max_length=160)
    location: Location | None = None
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity | None = None
    timestamp: datetime
    snapshot_url: str
    clip_url: str
    notes: str = Field(default="", max_length=4000)
    verification: Verification | None = None
    source: Literal["ai_detection", "simulation"] = "ai_detection"
    priority: Priority | None = None
    detection_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        return _timezone_aware(value)

    @field_validator("snapshot_url")
    @classmethod
    def safe_snapshot_url(cls, value: str) -> str:
        return _evidence_url(value)

    @field_validator("clip_url")
    @classmethod
    def safe_clip_url(cls, value: str) -> str:
        return _evidence_url(value, allow_clip=True)


class IncidentCreate(BaseModel):
    camera_id: str
    camera_name: str | None = None
    location: Location | None = None
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity | None = None
    timestamp: datetime | None = None
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification | None = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime | None) -> datetime | None:
        return _timezone_aware(value) if value is not None else None

    @field_validator("snapshot_url")
    @classmethod
    def safe_snapshot_url(cls, value: str) -> str:
        return _evidence_url(value)

    @field_validator("clip_url")
    @classmethod
    def safe_clip_url(cls, value: str) -> str:
        return _evidence_url(value, allow_clip=True)


class Evidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    type: str
    url: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_has_timezone(cls, value: datetime) -> datetime:
        return _timezone_aware(value)


class EvidenceCreate(BaseModel):
    incident_id: str
    type: str = "snapshot"
    url: str

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        return _evidence_url(value, allow_clip=True)


class WorkflowEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    type: Literal[
        "notification.sent",
        "notification.failed",
        "acknowledgement.received",
        "escalation.triggered",
        "workflow.completed",
    ]
    timestamp: datetime
    responder_id: str | None = Field(default=None, max_length=128)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        return _timezone_aware(value)


class AcknowledgeRequest(BaseModel):
    responder_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)


class ResolveRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    notes: str = Field(default="", max_length=4000)


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthToken(BaseModel):
    token: str
    user: dict[str, str]


class SimulateRequest(BaseModel):
    type: IncidentType
    camera_id: str = "cam_01"


class Stats(BaseModel):
    total: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    by_hour: list[dict[str, Any]]
    by_camera: list[dict[str, Any]]
