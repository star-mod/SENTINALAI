"""Base Detector and Common Data Structures for SentinelAI.
Implements sliding temporal verification windows, cooldown timers, and severity classification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import numpy as np


@dataclass
class TrackState:
    track_id: int
    bbox: List[float]  # [x1, y1, x2, y2]
    keypoints: Optional[np.ndarray] = None  # shape (17, 3) [x, y, conf]
    confidence: float = 1.0
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FrameState:
    camera_id: str
    frame_idx: int
    timestamp: float  # epoch seconds
    frame: Optional[np.ndarray] = None
    tracks: Dict[int, TrackState] = field(default_factory=dict)
    optical_flow: Optional[np.ndarray] = None
    mean_flow_mag: float = 0.0
    flow_divergence: float = 0.0


@dataclass
class Detection:
    incident_type: str
    camera_id: str
    confidence: float
    severity: str
    timestamp: str  # ISO-8601 UTC
    track_ids: List[int]
    verification: Dict[str, Any]
    description: str = ""

    @staticmethod
    def calculate_severity(confidence: float) -> str:
        """Shared Contract rule: confidence >= 0.85 -> high, >= 0.70 -> medium, else low."""
        if confidence >= 0.85:
            return "high"
        elif confidence >= 0.70:
            return "medium"
        return "low"


class BaseDetector:
    """Base class for all temporal verification safety detectors."""

    def __init__(self, name: str, camera_id: str, config: Dict[str, Any]):
        self.name = name
        self.camera_id = camera_id
        self.config = config
        self.enabled = config.get("enabled", True)
        self.window_seconds = float(config.get("window_seconds", 2.5))
        self.frames_required = int(config.get("frames_required", 15))
        self.confidence_min = float(config.get("confidence_min", 0.70))
        self.cooldown_seconds = float(config.get("cooldown_seconds", 20.0))

        # Internal state
        self.last_alert_time: float = -999.0
        self.history: List[FrameState] = []
        self.frame_confirmation_count: int = 0

    def prune_history(self, current_time: float):
        """Keep only frames within the sliding window."""
        cutoff = current_time - self.window_seconds
        self.history = [f for f in self.history if f.timestamp >= cutoff]

    def is_in_cooldown(self, current_time: float) -> bool:
        return (current_time - self.last_alert_time) < self.cooldown_seconds

    def update(self, frame_state: FrameState) -> Optional[Detection]:
        """Update detector with latest frame. Returns Detection if temporal condition is satisfied."""
        if not self.enabled:
            return None

        self.history.append(frame_state)
        self.prune_history(frame_state.timestamp)

        if self.is_in_cooldown(frame_state.timestamp):
            return None

        return self.analyze(frame_state)

    def analyze(self, current_frame: FrameState) -> Optional[Detection]:
        """Subclasses must implement temporal verification logic."""
        raise NotImplementedError

    def create_detection(
        self,
        incident_type: str,
        confidence: float,
        track_ids: List[int],
        frames_confirmed: int,
        description: str = ""
    ) -> Detection:
        """Factory method to construct a standard Detection object conforming to Shared Contract."""
        clamped_conf = min(max(float(confidence), 0.0), 1.0)
        severity = Detection.calculate_severity(clamped_conf)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        self.last_alert_time = self.history[-1].timestamp if self.history else 0.0
        self.frame_confirmation_count = 0  # reset upon triggering

        return Detection(
            incident_type=incident_type,
            camera_id=self.camera_id,
            confidence=round(clamped_conf, 2),
            severity=severity,
            timestamp=now_iso,
            track_ids=track_ids,
            verification={
                "window_seconds": self.window_seconds,
                "frames_confirmed": int(frames_confirmed),
                "frames_required": int(self.frames_required),
            },
            description=description,
        )


class DetectorRegistry:
    """Registry for plug-and-play detector instantiation."""
    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(subclass):
            cls._registry[name] = subclass
            return subclass
        return decorator

    @classmethod
    def create(cls, name: str, camera_id: str, config: Dict[str, Any]) -> Optional[BaseDetector]:
        detector_cls = cls._registry.get(name)
        if detector_cls is None:
            return None
        return detector_cls(camera_id=camera_id, config=config)

    @classmethod
    def available_detectors(cls) -> List[str]:
        return list(cls._registry.keys())
