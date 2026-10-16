"""Unit tests for SentinelAI detectors with synthetic keypoint and trajectory sequences.
Tests temporal verification persistence, positive triggers, and negative controls.
"""

import time
import numpy as np
import pytest

from sentinel_ai.detectors.base import FrameState, TrackState, Detection
from sentinel_ai.detectors.fall import FallDetector
from sentinel_ai.detectors.altercation import AltercationDetector
from sentinel_ai.detectors.crowd import CrowdDetector


def test_fall_detector_positive_and_negative():
    cfg = {
        "enabled": True,
        "window_seconds": 2.5,
        "frames_required": 10,
        "confidence_min": 0.70,
        "drop_velocity_threshold": 0.05,
        "aspect_ratio_threshold": 1.1,
        "stillness_threshold": 0.04,
        "cooldown_seconds": 10.0,
    }
    detector = FallDetector(camera_id="cam_01", config=cfg)

    # 1. Negative control: Upright walking person (should NOT trigger)
    t = 100.0
    for i in range(15):
        t += 0.066
        # Aspect ratio: w=60, h=150 -> 0.4 (upright)
        track = TrackState(
            track_id=1,
            bbox=[100.0 + i * 2, 200.0, 160.0 + i * 2, 350.0],
            keypoints=None,
        )
        fs = FrameState(camera_id="cam_01", frame_idx=i, timestamp=t, tracks={1: track})
        det = detector.update(fs)
        assert det is None, "Normal walking must not trigger fall detection"

    # 2. Positive test: Sudden drop followed by horizontal stillness
    # Frame 16: Upright
    t += 0.066
    track_drop_1 = TrackState(track_id=2, bbox=[300.0, 200.0, 360.0, 350.0])
    detector.update(FrameState("cam_01", 16, t, tracks={2: track_drop_1}))

    # Frame 17: Rapid downward drop in Y (center drops from 275 to 500)
    t += 0.066
    track_drop_2 = TrackState(track_id=2, bbox=[300.0, 480.0, 420.0, 560.0])
    detector.update(FrameState("cam_01", 17, t, tracks={2: track_drop_2}))

    # Frames 18..35: Horizontal posture (w=120, h=50 -> aspect ratio 2.4) and low motion
    detection_result = None
    for k in range(18, 35):
        t += 0.066
        track_fallen = TrackState(
            track_id=2,
            bbox=[310.0, 520.0, 430.0, 570.0],  # aspect ratio 120/50 = 2.4
            keypoints=None,
        )
        fs = FrameState(camera_id="cam_01", frame_idx=k, timestamp=t, tracks={2: track_fallen})
        det = detector.update(fs)
        if det is not None:
            detection_result = det
            break

    assert detection_result is not None, "Fall detector must trigger after sustained prone stillness"
    assert detection_result.incident_type == "fall_collapse"
    assert detection_result.confidence >= 0.70
    assert detection_result.verification["frames_confirmed"] >= 10


def test_altercation_detector_positive_and_negative():
    cfg = {
        "enabled": True,
        "window_seconds": 2.5,
        "frames_required": 12,
        "confidence_min": 0.70,
        "proximity_threshold": 0.25,
        "wrist_velocity_threshold": 0.05,
        "rapid_approach_threshold": 0.06,
        "cooldown_seconds": 10.0,
    }
    detector = AltercationDetector(camera_id="cam_02", config=cfg)

    # 1. Negative control: Two people walking past each other far apart
    t = 100.0
    for i in range(15):
        t += 0.066
        t1 = TrackState(1, [100.0 + i * 2, 300.0, 160.0 + i * 2, 450.0])
        t2 = TrackState(2, [800.0 - i * 2, 300.0, 860.0 - i * 2, 450.0])
        det = detector.update(FrameState("cam_02", i, t, tracks={1: t1, 2: t2}))
        assert det is None, "Distant walking tracks must not trigger altercation"

    # 2. Positive test: Close proximity + sustained high wrist speed
    det_result = None
    for k in range(16, 36):
        t += 0.066
        # Both people at x ~ 400 (very close)
        kp1 = np.zeros((17, 3), dtype=np.float32)
        kp2 = np.zeros((17, 3), dtype=np.float32)
        # Wrists at index 9, 10 swinging back and forth rapidly
        wrist_swing = 120.0 * np.sin(k * 1.5)
        kp1[9] = [420.0 + wrist_swing, 350.0, 0.9]
        kp1[10] = [420.0 - wrist_swing, 350.0, 0.9]
        kp2[9] = [460.0 - wrist_swing, 350.0, 0.9]
        kp2[10] = [460.0 + wrist_swing, 350.0, 0.9]

        t1 = TrackState(10, [400.0, 300.0, 450.0, 450.0], keypoints=kp1)
        t2 = TrackState(11, [440.0, 300.0, 490.0, 450.0], keypoints=kp2)
        det = detector.update(FrameState("cam_02", k, t, tracks={10: t1, 11: t2}))
        if det is not None:
            det_result = det
            break

    assert det_result is not None, "Altercation detector must trigger on sustained aggressive motion"
    assert det_result.incident_type == "physical_altercation"
    assert det_result.severity in ["medium", "high"]
    assert det_result.verification["frames_confirmed"] >= 12


def test_crowd_detector_positive_and_negative():
    cfg = {
        "enabled": True,
        "window_seconds": 2.5,
        "frames_required": 10,
        "confidence_min": 0.70,
        "optical_flow_spike_factor": 2.0,
        "direction_divergence_threshold": 0.35,
        "min_people_for_crowd": 3,
        "cooldown_seconds": 10.0,
    }
    detector = CrowdDetector(camera_id="cam_03", config=cfg)

    # 1. Establish baseline (15 calm frames)
    t = 100.0
    for i in range(15):
        t += 0.066
        tracks = {
            1: TrackState(1, [100.0, 300.0, 140.0, 400.0]),
            2: TrackState(2, [200.0, 300.0, 240.0, 400.0]),
            3: TrackState(3, [300.0, 300.0, 340.0, 400.0]),
            4: TrackState(4, [400.0, 300.0, 440.0, 400.0]),
        }
        det = detector.update(FrameState("cam_03", i, t, tracks=tracks, mean_flow_mag=2.0, flow_divergence=0.05))
        assert det is None

    # 2. Spike in flow magnitude and divergence (stampede/panic)
    det_result = None
    for k in range(16, 32):
        t += 0.066
        tracks = {
            1: TrackState(1, [100.0, 300.0, 140.0, 400.0]),
            2: TrackState(2, [200.0, 300.0, 240.0, 400.0]),
            3: TrackState(3, [300.0, 300.0, 340.0, 400.0]),
            4: TrackState(4, [400.0, 300.0, 440.0, 400.0]),
        }
        # 10.0 is 5x baseline (2.0)
        det = detector.update(FrameState("cam_03", k, t, tracks=tracks, mean_flow_mag=10.0, flow_divergence=0.75))
        if det is not None:
            det_result = det
            break

    assert det_result is not None, "Crowd detector must trigger on sustained optical flow spike"
    assert det_result.incident_type == "abnormal_crowd_movement"
    assert det_result.verification["frames_confirmed"] >= 10


def test_crowd_detector_real_world_baseline_regression():
    """Regression test: verifies that realistic CCTV low-magnitude optical flow (0.10 baseline)
    correctly triggers on surges (1.20+), while normal pedestrian variance does not trigger.
    """
    cfg = {
        "enabled": True,
        "window_seconds": 2.5,
        "frames_required": 10,
        "confidence_min": 0.70,
        "optical_flow_spike_factor": 2.2,
        "direction_divergence_threshold": 0.35,
        "min_people_for_crowd": 3,
        "cooldown_seconds": 10.0,
    }
    detector = CrowdDetector(camera_id="cam_03", config=cfg)

    # 1. Establish calm baseline with real-world CCTV values (~0.10 mag)
    t = 200.0
    tracks = {i: TrackState(i, [100.0 * i, 200.0, 100.0 * i + 40, 300.0]) for i in range(1, 5)}
    for i in range(20):
        t += 0.066
        fs = FrameState(camera_id="cam_03", frame_idx=i, timestamp=t, tracks=tracks, mean_flow_mag=0.10, flow_divergence=0.10)
        assert detector.update(fs) is None, "Calm baseline must not trigger alert"

    # 2. Negative test: minor walking speed increase (0.25 mag) - must not trigger
    for k in range(20, 35):
        t += 0.066
        fs = FrameState(camera_id="cam_03", frame_idx=k, timestamp=t, tracks=tracks, mean_flow_mag=0.25, flow_divergence=0.20)
        assert detector.update(fs) is None, "Normal pedestrian speed increase must not trigger"

    # 3. Positive test: crowd running surge (1.20 mag -> 6x baseline floor)
    triggered_det = None
    for j in range(35, 55):
        t += 0.066
        fs = FrameState(camera_id="cam_03", frame_idx=j, timestamp=t, tracks=tracks, mean_flow_mag=1.20, flow_divergence=0.80)
        det = detector.update(fs)
        if det is not None:
            triggered_det = det
            break

    assert triggered_det is not None, "Real-world crowd surge must trigger detection after 10 confirmed frames"
    assert triggered_det.incident_type == "abnormal_crowd_movement"
    assert triggered_det.verification["frames_confirmed"] >= 10

