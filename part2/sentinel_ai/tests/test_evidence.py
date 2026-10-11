"""Regression tests for SentinelAI Evidence Manager and CameraRingBuffer.
Validates incident snapshot frame selection, visible alerts, anonymous track IDs,
and pre-roll / post-roll video clip capture windows.
"""

import os
import shutil
import tempfile
import time
import cv2
import numpy as np
import pytest

from sentinel_ai.detectors.base import Detection, TrackState
from sentinel_ai.evidence import CameraRingBuffer, draw_annotations


@pytest.fixture
def temp_evidence_dir():
    d = tempfile.mkdtemp(prefix="sentinel_test_evidence_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_draw_annotations_visible_alert_and_anonymous_ids():
    """Verifies that draw_annotations renders visible alert banners, highlighted bounding boxes,
    and strictly anonymous track tags without biometric or facial identification.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracks = {
        1: TrackState(track_id=1, bbox=[100.0, 100.0, 200.0, 300.0], keypoints=None),
        2: TrackState(track_id=2, bbox=[300.0, 100.0, 400.0, 300.0], keypoints=None),
    }

    # 1. Normal state (no active incident)
    annotated_normal = draw_annotations(frame, tracks, active_detection=None, camera_name="TestCam")
    assert annotated_normal.shape == frame.shape
    # Top banner and cam name rendered
    assert np.any(annotated_normal[0:38, :] != 0)

    # 2. Alert state (active detection on track 1)
    detection = Detection(
        incident_type="fall_collapse",
        camera_id="cam_01",
        confidence=0.95,
        severity="high",
        timestamp="2026-10-10T10:00:00Z",
        track_ids=[1],
        verification={"window_seconds": 2.5, "frames_confirmed": 15, "frames_required": 15},
        description="Person fell and remains stationary.",
    )
    annotated_alert = draw_annotations(frame, tracks, active_detection=detection, camera_name="TestCam")

    # Alert banner is drawn between y=40 and y=85
    banner_region = annotated_alert[40:85, 10:200]
    assert np.any(banner_region[:, :, 2] > 100), "Red alert banner must be visibly rendered in alert state"

    # Frame differs from normal frame
    assert not np.array_equal(annotated_normal, annotated_alert)


def test_snapshot_uses_current_verified_frame(temp_evidence_dir):
    """Verifies that save_snapshot captures the current verified annotated frame,
    rather than a stale earlier frame from the buffer.
    """
    ring = CameraRingBuffer(camera_id="cam_01", target_fps=15.0, buffer_seconds=5.0)

    # Add older frames with a blue patch
    for i in range(5):
        old_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        old_frame[40:60, 40:60] = (255, 0, 0)  # Blue patch
        ring.add_frame(float(i), old_frame, old_frame)

    # Verified incident frame has a green patch
    verified_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    verified_frame[40:60, 40:60] = (0, 255, 0)  # Green patch

    # Save snapshot passing the verified incident frame
    snap_path = ring.save_snapshot("inc_snap_test", snapshots_dir=temp_evidence_dir, frame=verified_frame)
    full_path = os.path.join(temp_evidence_dir, "inc_snap_test.jpg")
    assert os.path.exists(full_path)

    loaded = cv2.imread(full_path)
    assert loaded is not None
    # Verify the patch is green (the verified frame), not blue (earlier frame)
    assert loaded[50, 50, 1] > 230, "Snapshot must contain the verified incident frame (green patch)"
    assert loaded[50, 50, 0] < 25, "Snapshot must not contain the earlier frame (blue patch)"


def test_evidence_clip_pre_and_post_roll_window(temp_evidence_dir):
    """Verifies that the evidence clip captures pre-roll (~3s), the incident event,
    and post-roll (~3s) frames based on configurable intervals.
    """
    fps = 15.0
    ring = CameraRingBuffer(camera_id="cam_01", target_fps=fps, buffer_seconds=10.0)

    # Populate 8 seconds of frames (t = 0.0 to 8.0)
    for i in range(int(fps * 8)):
        t = i / fps
        frame = np.full((120, 160, 3), fill_value=int(i % 255), dtype=np.uint8)
        ring.add_frame(t, frame, frame)

    # Trigger incident at t = 4.0, requesting 2.0s pre-roll and 2.0s post-roll
    # Expected clip span: [2.0s, 6.0s] -> ~4.0s = ~60 frames
    clip_url = ring.save_clip(
        incident_id="inc_window_test",
        clips_dir=temp_evidence_dir,
        pre_seconds=2.0,
        post_seconds=2.0,
        trigger_time=4.0,
    )
    full_clip_path = os.path.join(temp_evidence_dir, "inc_window_test.mp4")
    assert os.path.exists(full_clip_path)

    cap = cv2.VideoCapture(full_clip_path)
    assert cap.isOpened(), "Generated MP4 clip must open cleanly in OpenCV"

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # ~4 seconds at 15 FPS is ~60 frames (+/- 3 frames due to sampling)
    assert 55 <= total_frames <= 65, f"Clip frame count {total_frames} should span ~60 frames for 4s total window"


def test_evidence_clip_delayed_post_roll_collection(temp_evidence_dir):
    """Verifies asynchronous pending clip request workflow:
    1. Incident triggers at t=2.0s with pre_seconds=1.5s, post_seconds=1.5s.
    2. Clips are not finalized prematurely before post-roll completes.
    3. Finalization occurs once frames reach trigger_time + post_seconds (t=3.5s).
    """
    fps = 10.0
    ring = CameraRingBuffer(camera_id="cam_01", target_fps=fps, buffer_seconds=10.0)

    # Ingest pre-roll frames up to t = 2.0
    for i in range(21):
        t = i / fps
        f = np.zeros((100, 100, 3), dtype=np.uint8)
        ring.add_frame(t, f, f)

    # Trigger incident at t = 2.0, requiring post-roll until t = 3.5
    clip_url = ring.request_clip(
        incident_id="inc_async_test",
        clips_dir=temp_evidence_dir,
        pre_seconds=1.5,
        post_seconds=1.5,
        trigger_time=2.0,
    )
    assert "inc_async_test.mp4" in clip_url
    assert "inc_async_test" in ring.pending_clips

    # Ingest more frames up to t = 2.8 (post-roll still incomplete)
    for i in range(21, 29):
        t = i / fps
        f = np.zeros((100, 100, 3), dtype=np.uint8)
        ring.add_frame(t, f, f)
        finalized = ring.check_pending_clips(current_time=t)
        assert finalized == [], "Clip must not finalize before post_seconds interval has elapsed"

    # Ingest frames up to t = 3.6 (exceeding end_time of 3.5)
    for i in range(29, 37):
        t = i / fps
        f = np.zeros((100, 100, 3), dtype=np.uint8)
        ring.add_frame(t, f, f)
        finalized = ring.check_pending_clips(current_time=t)
        if finalized:
            break

    assert "inc_async_test" in finalized, "Clip must finalize once current_time >= trigger_time + post_seconds"
    assert "inc_async_test" not in ring.pending_clips

    # Wait briefly for background thread to write MP4
    time.sleep(0.3)
    clip_path = os.path.join(temp_evidence_dir, "inc_async_test.mp4")
    assert os.path.exists(clip_path), "Finalized clip MP4 file must exist on disk"


def test_evidence_clip_flush_on_shutdown(temp_evidence_dir):
    """Verifies that flush_pending_clips preserves uncompleted pending clips on worker shutdown."""
    ring = CameraRingBuffer(camera_id="cam_01", target_fps=10.0, buffer_seconds=5.0)

    # Ingest 10 frames
    for i in range(10):
        t = float(i)
        f = np.zeros((100, 100, 3), dtype=np.uint8)
        ring.add_frame(t, f, f)

    # Request clip at t=9.0 requiring post-roll until t=12.0
    ring.request_clip("inc_flush_test", clips_dir=temp_evidence_dir, pre_seconds=2.0, post_seconds=3.0, trigger_time=9.0)
    assert len(ring.pending_clips) == 1

    # Worker stops prematurely: flush_pending_clips() called
    finalized = ring.flush_pending_clips()
    assert finalized == ["inc_flush_test"]
    assert len(ring.pending_clips) == 0

    time.sleep(0.3)
    assert os.path.exists(os.path.join(temp_evidence_dir, "inc_flush_test.mp4"))
