"""Pydantic data schemas strictly conforming to SentinelAI Shared Contract.
"""

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lng: float
    label: str


class Verification(BaseModel):
    window_seconds: float = 2.5
    frames_confirmed: int = 30
    frames_required: int = 25


class Incident(BaseModel):
    id: str
    camera_id: str
    camera_name: str
    location: Location
    type: Literal["physical_altercation", "fall_collapse", "abnormal_crowd_movement", "vehicle_accident"]
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Literal["low", "medium", "high"]
    timestamp: str  # ISO-8601 UTC
    status: Literal["new", "acknowledged", "resolved"] = "new"
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification


class Camera(BaseModel):
    id: str
    name: str
    location: Location
    status: Literal["online", "offline"] = "online"
    stream_url: str


class IncidentPatchRequest(BaseModel):
    status: Optional[Literal["new", "acknowledged", "resolved"]] = None
    notes: Optional[str] = None


class SimulateRequest(BaseModel):
    type: Literal["physical_altercation", "fall_collapse", "abnormal_crowd_movement", "vehicle_accident"]
    camera_id: str = "cam_01"


class InternalIncidentCreate(BaseModel):
    camera_id: str
    camera_name: str
    location: Location
    type: Literal["physical_altercation", "fall_collapse", "abnormal_crowd_movement", "vehicle_accident"]
    confidence: float
    severity: Literal["low", "medium", "high"]
    timestamp: str
    snapshot_url: str
    clip_url: str
    notes: str = ""
    verification: Verification


class StatsResponse(BaseModel):
    total: int
    by_type: Dict[str, int]
    by_status: Dict[str, int]
    by_hour: List[Dict[str, Any]]
    by_camera: List[Dict[str, Any]]
