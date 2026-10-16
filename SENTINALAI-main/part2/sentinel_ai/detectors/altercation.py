"""Physical Altercation Detector for SentinelAI.
Detects >= 2 tracks in close proximity with sustained high wrist/arm velocity
or rapid approach/retreat over a temporal verification sliding window.
"""

from typing import Dict, List, Optional, Any, Tuple, Set
import numpy as np
from sentinel_ai.detectors.base import BaseDetector, FrameState, Detection, DetectorRegistry, TrackState


@DetectorRegistry.register("physical_altercation")
class AltercationDetector(BaseDetector):
    def __init__(self, camera_id: str, config: Dict[str, Any]):
        super().__init__("physical_altercation", camera_id, config)
        self.proximity_threshold = float(config.get("proximity_threshold", 0.22))
        self.wrist_velocity_threshold = float(config.get("wrist_velocity_threshold", 0.05))
        self.rapid_approach_threshold = float(config.get("rapid_approach_threshold", 0.07))

        # Track pair confirmation: (tid1, tid2) sorted tuple -> confirmation count
        self.pair_confirmed_frames: Dict[Tuple[int, int], int] = {}
        self.pair_energy_history: Dict[Tuple[int, int], List[float]] = {}

    def _get_center(self, bbox: List[float], frame_w: int = 1920, frame_h: int = 1080) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0) / frame_w, ((y1 + y2) / 2.0) / frame_h

    def _get_wrist_velocity(
        self,
        curr_track: TrackState,
        prev_track: TrackState,
        dt: float,
        frame_w: int = 1920,
        frame_h: int = 1080
    ) -> float:
        """Calculates normalized wrist velocity between frames."""
        if curr_track.keypoints is None or prev_track.keypoints is None:
            # Fallback to bbox expansion/movement velocity
            dx = (curr_track.bbox[2] - curr_track.bbox[0]) - (prev_track.bbox[2] - prev_track.bbox[0])
            dy = (curr_track.bbox[3] - curr_track.bbox[1]) - (prev_track.bbox[3] - prev_track.bbox[1])
            return float(np.sqrt(dx**2 + dy**2) / (frame_w * max(dt, 0.01)))

        kp_curr = curr_track.keypoints
        kp_prev = prev_track.keypoints
        if len(kp_curr) < 11 or len(kp_prev) < 11:
            return 0.0

        # Wrists are indices 9 (left) and 10 (right)
        velocities = []
        for wrist_idx in [9, 10]:
            if kp_curr[wrist_idx, 2] > 0.3 and kp_prev[wrist_idx, 2] > 0.3:
                dx = (kp_curr[wrist_idx, 0] - kp_prev[wrist_idx, 0]) / frame_w
                dy = (kp_curr[wrist_idx, 1] - kp_prev[wrist_idx, 1]) / frame_h
                v = float(np.sqrt(dx**2 + dy**2) / max(dt, 0.01))
                velocities.append(v)

        return max(velocities) if velocities else 0.0

    def analyze(self, current_frame: FrameState) -> Optional[Detection]:
        if len(self.history) < 3:
            return None

        tracks = current_frame.tracks
        track_ids = list(tracks.keys())
        if len(track_ids) < 2:
            return None

        dt = current_frame.timestamp - self.history[-2].timestamp if len(self.history) >= 2 else 0.066
        prev_tracks = self.history[-2].tracks if len(self.history) >= 2 else {}

        active_pairs: Set[Tuple[int, int]] = set()

        for i in range(len(track_ids)):
            for j in range(i + 1, len(track_ids)):
                id1, id2 = sorted([track_ids[i], track_ids[j]])
                pair_key = (id1, id2)
                t1 = tracks[id1]
                t2 = tracks[id2]

                c1 = self._get_center(t1.bbox)
                c2 = self._get_center(t2.bbox)
                dist = np.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)

                # Are they in close interpersonal physical proximity?
                if dist <= self.proximity_threshold:
                    active_pairs.add(pair_key)

                    # Measure wrist/arm speeds if both tracks existed previously
                    v1 = self._get_wrist_velocity(t1, prev_tracks[id1], dt) if id1 in prev_tracks else 0.0
                    v2 = self._get_wrist_velocity(t2, prev_tracks[id2], dt) if id2 in prev_tracks else 0.0
                    max_wrist_v = max(v1, v2)

                    # Relative approach/retreat oscillation
                    approach_rate = 0.0
                    if id1 in prev_tracks and id2 in prev_tracks:
                        prev_c1 = self._get_center(prev_tracks[id1].bbox)
                        prev_c2 = self._get_center(prev_tracks[id2].bbox)
                        prev_dist = np.sqrt((prev_c1[0] - prev_c2[0]) ** 2 + (prev_c1[1] - prev_c2[1]) ** 2)
                        approach_rate = abs(dist - prev_dist) / max(dt, 0.01)

                    # Check altercation motion criteria
                    is_violent_motion = (
                        max_wrist_v >= self.wrist_velocity_threshold
                        or approach_rate >= self.rapid_approach_threshold
                        or (max_wrist_v > 0.035 and approach_rate > 0.04)
                    )

                    energy_score = max_wrist_v + approach_rate
                    if pair_key not in self.pair_energy_history:
                        self.pair_energy_history[pair_key] = []
                    self.pair_energy_history[pair_key].append(energy_score)
                    if len(self.pair_energy_history[pair_key]) > 30:
                        self.pair_energy_history[pair_key].pop(0)

                    if is_violent_motion:
                        self.pair_confirmed_frames[pair_key] = self.pair_confirmed_frames.get(pair_key, 0) + 1
                    else:
                        # Slight decay
                        if pair_key in self.pair_confirmed_frames:
                            self.pair_confirmed_frames[pair_key] = max(0, self.pair_confirmed_frames[pair_key] - 1)
                else:
                    # Decay if separated
                    if pair_key in self.pair_confirmed_frames:
                        self.pair_confirmed_frames[pair_key] = max(0, self.pair_confirmed_frames[pair_key] - 2)

        # Check for confirmed pair
        for pair_key, confirmed in list(self.pair_confirmed_frames.items()):
            if confirmed >= self.frames_required:
                id1, id2 = pair_key
                energies = self.pair_energy_history.get(pair_key, [0.1])
                avg_energy = float(np.mean(energies)) if energies else 0.1
                base_conf = 0.76 + min(avg_energy * 0.8, 0.15) + (0.05 * min(confirmed / self.frames_required, 1.2))
                confidence = min(max(base_conf, self.confidence_min), 0.95)

                self.pair_confirmed_frames.pop(pair_key, None)
                self.pair_energy_history.pop(pair_key, None)

                return self.create_detection(
                    incident_type="physical_altercation",
                    confidence=confidence,
                    track_ids=[id1, id2],
                    frames_confirmed=confirmed,
                    description=f"Physical altercation detected between tracks {id1} and {id2} with sustained aggressive motion ({confirmed} frames confirmed over {self.window_seconds}s window)."
                )

        return None
