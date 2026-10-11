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


class IncidentPatch(BaseModel):
    status: IncidentStatus | None = None
    notes: str | None = None


class InternalIncident(BaseModel):
    camera_id: str
    camera_name: str
    location: Location
    type: IncidentType
    confidence: float = Field(ge=0, le=1)
    severity: Severity | None = None
    timestamp: str
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification


class SimulateRequest(BaseModel):
    type: IncidentType
    camera_id: str = "cam_01"


class Stats(BaseModel):
    total: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    by_hour: list[dict[str, Any]]
    by_camera: list[dict[str, Any]]