from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


IncidentType = Literal["physical_altercation", "fall_collapse", "abnormal_crowd_movement"]
IncidentStatus = Literal["new", "acknowledged", "resolved"]
Severity = Literal["low", "medium", "high"]


class Location(BaseModel):
    lat: float
    lng: float
    label: str


class Verification(BaseModel):
    window_seconds: float = 2.5
    frames_confirmed: int = 30
    frames_required: int = 25


class Incident(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_id: str
    camera_name: str
    location: Location
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity
    timestamp: str
    status: IncidentStatus
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification


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


class InternalIncident(BaseModel):
    camera_id: str
    camera_name: str | None = None
    location: Location | None = None
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity | None = None
    timestamp: str
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification | None = None


class IncidentCreate(BaseModel):
    camera_id: str
    camera_name: str | None = None
    location: Location | None = None
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity | None = None
    timestamp: str | None = None
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    type: str
    url: str
    created_at: str


class EvidenceCreate(BaseModel):
    incident_id: str
    type: str = "snapshot"
    url: str


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