"""Abnormal Crowd Movement Detector for SentinelAI.
Detects surges, panics, and rapid crowd dispersion using optical-flow speed spikes
and direction divergence vs rolling baseline across person tracks.
"""

from typing import Dict, List, Optional, Any
import numpy as np
from sentinel_ai.detectors.base import BaseDetector, FrameState, Detection, DetectorRegistry


@DetectorRegistry.register("abnormal_crowd_movement")
class CrowdDetector(BaseDetector):
    def __init__(self, camera_id: str, config: Dict[str, Any]):
        super().__init__("abnormal_crowd_movement", camera_id, config)
        self.optical_flow_spike_factor = float(config.get("optical_flow_spike_factor", 2.0))
        self.direction_divergence_threshold = float(config.get("direction_divergence_threshold", 0.40))
        self.min_people_for_crowd = int(config.get("min_people_for_crowd", 3))

        # Rolling baseline of flow magnitude and tracks velocity
        self.flow_baseline: List[float] = []
        self.divergence_baseline: List[float] = []
        self.confirmation_counter: int = 0
        self.peak_spike_ratio: float = 1.0

    def analyze(self, current_frame: FrameState) -> Optional[Detection]:
        tracks = current_frame.tracks
        num_people = len(tracks)

        # Compute flow magnitude and track motion energy
        current_flow_mag = current_frame.mean_flow_mag
        current_divergence = current_frame.flow_divergence

        # If optical flow was not precomputed on frame, estimate from track velocities
        track_speeds: List[float] = []
        track_angles: List[float] = []

        if len(self.history) >= 2:
            prev_tracks = self.history[-2].tracks
            dt = max(current_frame.timestamp - self.history[-2].timestamp, 0.01)

            for tid, track in tracks.items():
                if tid in prev_tracks:
                    prev_track = prev_tracks[tid]
                    c_curr = ((track.bbox[0] + track.bbox[2]) / 2.0, (track.bbox[1] + track.bbox[3]) / 2.0)
                    c_prev = ((prev_track.bbox[0] + prev_track.bbox[2]) / 2.0, (prev_track.bbox[1] + prev_track.bbox[3]) / 2.0)
                    dx = c_curr[0] - c_prev[0]
                    dy = c_curr[1] - c_prev[1]
                    speed = float(np.sqrt(dx**2 + dy**2) / dt)
                    track_speeds.append(speed)
                    angle = float(np.arctan2(dy, dx))
                    track_angles.append(angle)

        if current_flow_mag <= 0.0 and track_speeds:
            current_flow_mag = float(np.mean(track_speeds))

        if current_divergence <= 0.0 and len(track_angles) >= 2:
            # Measure angular variance / divergence (circular variance approximation)
            cos_mean = np.mean(np.cos(track_angles))
            sin_mean = np.mean(np.sin(track_angles))
            r = np.sqrt(cos_mean**2 + sin_mean**2)
            current_divergence = float(1.0 - r)  # 0 = all same direction, 1 = maximum dispersion

        # Update rolling baseline (use up to 60 previous normal frames)
        if len(self.flow_baseline) < 10:
            self.flow_baseline.append(max(current_flow_mag, 0.20))
            if current_divergence > 0.0:
                self.divergence_baseline.append(current_divergence)
            return None

        baseline_mag = float(np.median(self.flow_baseline))
        baseline_mag = max(baseline_mag, 0.20)
        spike_ratio = current_flow_mag / baseline_mag

        # Check abnormal criteria
        is_spike = spike_ratio >= self.optical_flow_spike_factor
        is_divergent = current_divergence >= self.direction_divergence_threshold and spike_ratio > 1.3
        has_crowd_size = num_people >= self.min_people_for_crowd or (spike_ratio > 2.8)

        if (is_spike or is_divergent) and has_crowd_size:
            self.confirmation_counter += 1
            self.peak_spike_ratio = max(self.peak_spike_ratio, spike_ratio)
        else:
            self.confirmation_counter = max(0, self.confirmation_counter - 1)
            # Add to normal baseline if not in abnormal state
            self.flow_baseline.append(current_flow_mag)
            if len(self.flow_baseline) > 60:
                self.flow_baseline.pop(0)

        if self.confirmation_counter >= self.frames_required:
            confirmed = self.confirmation_counter
            base_conf = 0.76 + min((self.peak_spike_ratio - 1.0) * 0.08, 0.16)
            confidence = min(max(base_conf, self.confidence_min), 0.94)

            involved_tracks = list(tracks.keys())[:8]  # list up to 8 representative tracks
            self.confirmation_counter = 0
            self.peak_spike_ratio = 1.0

            return self.create_detection(
                incident_type="abnormal_crowd_movement",
                confidence=confidence,
                track_ids=involved_tracks,
                frames_confirmed=confirmed,
                description=f"Abnormal crowd surge / divergence detected across {num_people} tracks with flow spike {spike_ratio:.1f}x baseline ({confirmed} frames confirmed over {self.window_seconds}s window)."
            )

        return None
