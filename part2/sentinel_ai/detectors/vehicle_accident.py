"""Vehicle Accident Detector for SentinelAI.
Detects potential vehicle crashes based on sudden velocity changes,
impact signatures, and bounding box deformation.
"""

from typing import Dict, List, Optional, Any, Tuple
import numpy as np
from sentinel_ai.detectors.base import BaseDetector, FrameState, Detection, DetectorRegistry, TrackState

@DetectorRegistry.register("vehicle_accident")
class VehicleAccidentDetector(BaseDetector):
    def __init__(self, camera_id: str, config: Dict[str, Any]):
        super().__init__("vehicle_accident", camera_id, config)
        # Threshold for sudden deceleration (normalized pixels/frame)
        self.deceleration_threshold = float(config.get("deceleration_threshold", 0.03))
        # Threshold for aspect ratio change (indicating a flip or heavy impact)
        self.deformation_threshold = float(config.get("deformation_threshold", 0.08))

        # Track vehicle states: track_id -> {last_vel, last_aspect, timestamp}
        self.vehicle_history: Dict[int, Dict[str, Any]] = {}

    def analyze(self, current_frame: FrameState) -> Optional[Detection]:
        # YOLO class indices for vehicles in COCO: 2: car, 3: motorcycle, 5: bus, 7: truck
        VEHICLE_CLASSES = {2, 3, 5, 7}

        tracks = current_frame.tracks
        track_ids = list(tracks.keys())

        # 1. INSTANT TRIGGER (Safety Net): Extreme Deformation
        # If any object looks like a crashed vehicle (very flat/wide), trigger immediately
        for tid, track in tracks.items():
            x1, y1, x2, y2 = track.bbox
            w = x2 - x1
            h = y2 - y1
            aspect_ratio = w / h if h > 0 else 1.0

            if aspect_ratio > 2.0:
                return self.create_detection(
                    incident_type="vehicle_accident",
                    confidence=0.85,
                    track_ids=[tid],
                    frames_confirmed=1,
                    description=f"Instant accident detection: Extreme vehicle deformation detected on track {tid}."
                )

        # 2. Check for Collision / Interaction (High Sensitivity)
        for i in range(len(track_ids)):
            for j in range(i + 1, len(track_ids)):
                t1 = tracks[track_ids[i]]
                t2 = tracks[track_ids[j]]

                box1 = t1.bbox
                box2 = t2.bbox

                x_left = max(box1[0], box2[0])
                y_top = max(box1[1], box2[1])
                x_right = min(box1[2], box2[2])
                y_bottom = min(box1[3], box2[3])

                if x_right > x_left and y_bottom > y_top:
                    intersection_area = (x_right - x_left) * (y_bottom - y_top)
                    if intersection_area > 100:
                        return self.create_detection(
                            incident_type="vehicle_accident",
                            confidence=0.90,
                            track_ids=[track_ids[i], track_ids[j]],
                            frames_confirmed=1,
                            description=f"Vehicle interaction/collision detected between track {track_ids[i]} and {track_ids[j]}."
                        )

        # 3. Check for Individual Impact/Deformation (Temporal)
        for track_id, track in tracks.items():
            x1, y1, x2, y2 = track.bbox
            w = x2 - x1
            h = y2 - y1
            aspect_ratio = w / h if h > 0 else 1.0
            center = np.array([(x1 + x2) / 2, (y1 + y2) / 2])

            if track_id in self.vehicle_history:
                prev = self.vehicle_history[track_id]
                prev_center = np.array(prev["center"])

                velocity = np.linalg.norm(center - prev_center)
                prev_velocity = prev["velocity"]
                deceleration = prev_velocity - velocity
                deformation = abs(aspect_ratio - prev["aspect"])

                if (deceleration > self.deceleration_threshold and velocity < 3.0) or (deformation > self.deformation_threshold):
                    return self.create_detection(
                        incident_type="vehicle_accident",
                        confidence=0.80,
                        track_ids=[track_id],
                        frames_confirmed=1,
                        description=f"Vehicle impact detected on track {track_id}. Decel: {deceleration:.2f}, Def: {deformation:.2f}"
                    )

            # Update history
            self.vehicle_history[track_id] = {
                "center": center.tolist(),
                "velocity": np.linalg.norm(center - np.array(self.vehicle_history[track_id].get("center", center))) if track_id in self.vehicle_history else 0.0,
                "aspect": aspect_ratio,
                "timestamp": current_frame.timestamp
            }

        return None