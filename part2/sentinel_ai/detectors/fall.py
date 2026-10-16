"""Fall & Collapse Detector for SentinelAI.
Detects rapid downward vertical drop of head/hip, followed by horizontal posture and low motion.
Verified over a temporal sliding window.
"""

from typing import Dict, List, Optional, Any, Tuple
import numpy as np
from sentinel_ai.detectors.base import BaseDetector, FrameState, Detection, DetectorRegistry, TrackState


@DetectorRegistry.register("fall_collapse")
class FallDetector(BaseDetector):
    def __init__(self, camera_id: str, config: Dict[str, Any]):
        super().__init__("fall_collapse", camera_id, config)
        self.drop_velocity_threshold = float(config.get("drop_velocity_threshold", 0.04))
        self.aspect_ratio_threshold = float(config.get("aspect_ratio_threshold", 0.9))
        self.stillness_threshold = float(config.get("stillness_threshold", 0.06))

        # Track confirmation counts per track_id: track_id -> int
        self.track_confirmed_frames: Dict[int, int] = {}
        # Track initial drop detected: track_id -> (timestamp, drop_magnitude)
        self.track_drop_events: Dict[int, Tuple[float, float]] = {}

    def _extract_posture_metrics(self, track: TrackState, frame_h: int = 1080, frame_w: int = 1920) -> Dict[str, float]:
        """Calculates normalized center, aspect ratio, vertical position, and keypoint orientation."""
        x1, y1, x2, y2 = track.bbox
        w = max(float(x2 - x1), 1.0)
        h = max(float(y2 - y1), 1.0)
        aspect_ratio = w / h
        norm_center_y = ((y1 + y2) / 2.0) / frame_h
        norm_center_x = ((x1 + x2) / 2.0) / frame_w

        head_y = None
        hip_y = None
        torso_angle_horizontal = False

        if track.keypoints is not None and len(track.keypoints) >= 17:
            kp = track.keypoints
            # Nose = 0, Shoulders = 5, 6, Hips = 11, 12
            nose_conf = kp[0, 2] if kp.shape[1] > 2 else 1.0
            if nose_conf > 0.3:
                head_y = float(kp[0, 1]) / frame_h

            hips_conf = (kp[11, 2] + kp[12, 2]) / 2.0 if kp.shape[1] > 2 else 1.0
            if hips_conf > 0.3:
                hip_y = float(kp[11, 1] + kp[12, 1]) / (2.0 * frame_h)

            shoulders_conf = (kp[5, 2] + kp[6, 2]) / 2.0 if kp.shape[1] > 2 else 1.0
            if hips_conf > 0.3 and shoulders_conf > 0.3:
                s_x = float(kp[5, 0] + kp[6, 0]) / 2.0
                s_y = float(kp[5, 1] + kp[6, 1]) / 2.0
                h_x = float(kp[11, 0] + kp[12, 0]) / 2.0
                h_y = float(kp[11, 1] + kp[12, 1]) / 2.0
                dx = abs(h_x - s_x)
                dy = abs(h_y - s_y)
                # If horizontal span is larger or near vertical span, person is prone/supine
                if dx > dy * 0.75:
                    torso_angle_horizontal = True

        return {
            "aspect_ratio": aspect_ratio,
            "center_x": norm_center_x,
            "center_y": norm_center_y,
            "head_y": head_y if head_y is not None else norm_center_y,
            "hip_y": hip_y if hip_y is not None else norm_center_y,
            "horizontal_torso": 1.0 if torso_angle_horizontal else 0.0,
            "bbox_h": h / frame_h,
        }

    def analyze(self, current_frame: FrameState) -> Optional[Detection]:
        if len(self.history) < 2:
            return None

        # Clean stale track records
        current_track_ids = set(current_frame.tracks.keys())
        for tid in list(self.track_confirmed_frames.keys()):
            if tid not in current_track_ids:
                self.track_confirmed_frames[tid] = max(0, self.track_confirmed_frames[tid] - 1)
                if self.track_confirmed_frames[tid] == 0:
                    self.track_confirmed_frames.pop(tid, None)
                    self.track_drop_events.pop(tid, None)

        for track_id, track in current_frame.tracks.items():
            curr_metrics = self._extract_posture_metrics(track)

            # 1. INSTANT TRIGGER (Safety Net): Extremely prone posture
            # If a person is suddenly very flat, trigger immediately regardless of history
            if curr_metrics["aspect_ratio"] > 1.5 or curr_metrics["horizontal_torso"] > 0.8:
                return self.create_detection(
                    incident_type="fall_collapse",
                    confidence=0.85,
                    track_ids=[track_id],
                    frames_confirmed=self.frames_required,
                    description=f"Instant fall detection: Extreme prone posture detected on track {track_id}."
                )

            # 2. TEMPORAL TRIGGER (Existing Logic)
            has_rapid_drop = False
            drop_magnitude = 0.0

            for prev_frame in self.history[:-2]:
                if track_id in prev_frame.tracks:
                    prev_track = prev_frame.tracks[track_id]
                    prev_metrics = self._extract_posture_metrics(prev_track)
                    dy_hip = curr_metrics["hip_y"] - prev_metrics["hip_y"]
                    dy_center = curr_metrics["center_y"] - prev_metrics["center_y"]
                    dy_head = curr_metrics["head_y"] - prev_metrics["head_y"]
                    max_dy = max(dy_hip, dy_center, dy_head)
                    dh = prev_metrics["bbox_h"] - curr_metrics["bbox_h"]

                    if max_dy > self.drop_velocity_threshold or dh > 0.10:
                        has_rapid_drop = True
                        drop_magnitude = max(max_dy, dh)
                        self.track_drop_events[track_id] = (prev_frame.timestamp, drop_magnitude)
                        break

            if track_id in self.track_drop_events:
                drop_ts, drop_mag = self.track_drop_events[track_id]
                if (current_frame.timestamp - drop_ts) <= self.window_seconds:
                    has_rapid_drop = True
                    drop_magnitude = max(drop_magnitude, drop_mag)

            is_prone = (
                curr_metrics["aspect_ratio"] >= self.aspect_ratio_threshold
                or curr_metrics["horizontal_torso"] > 0.5
                or (curr_metrics["aspect_ratio"] > 0.8 and curr_metrics["bbox_h"] < 0.25)
            )

            is_still = False
            if len(self.history) >= 2 and track_id in self.history[-2].tracks:
                last_metrics = self._extract_posture_metrics(self.history[-2].tracks[track_id])
                motion = np.sqrt(
                    (curr_metrics["center_x"] - last_metrics["center_x"]) ** 2
                    + (curr_metrics["center_y"] - last_metrics["center_y"]) ** 2
                )
                if motion < self.stillness_threshold:
                    is_still = True

            if has_rapid_drop and (is_prone or is_still):
                self.track_confirmed_frames[track_id] = self.track_confirmed_frames.get(track_id, 0) + 1
            elif is_prone and is_still and (track_id in self.track_drop_events):
                self.track_confirmed_frames[track_id] = self.track_confirmed_frames.get(track_id, 0) + 1
            else:
                if track_id in self.track_confirmed_frames:
                    self.track_confirmed_frames[track_id] = max(0, self.track_confirmed_frames[track_id] - 1)

            confirmed = self.track_confirmed_frames.get(track_id, 0)
            if confirmed >= self.frames_required:
                persistence_factor = min(confirmed / float(self.frames_required), 1.5) / 1.5
                base_conf = 0.75 + min(drop_magnitude * 1.5, 0.15) + (0.10 * persistence_factor)
                confidence = min(max(base_conf, self.confidence_min), 0.96)
                self.track_confirmed_frames.pop(track_id, None)
                self.track_drop_events.pop(track_id, None)
                return self.create_detection(
                    incident_type="fall_collapse",
                    confidence=confidence,
                    track_ids=[track_id],
                    frames_confirmed=confirmed,
                    description=f"Person collapse detected on track {track_id} with sustained horizontal posture ({confirmed} frames confirmed)."
                )

        return None
