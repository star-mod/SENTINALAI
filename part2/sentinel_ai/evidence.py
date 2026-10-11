"""Evidence Manager for SentinelAI.
Maintains rolling temporal ring buffers per camera, annotates video frames with
pose skeletons and incident overlays, and renders snapshot JPEGs and MP4 clips.
"""

import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np

from sentinel_ai.detectors.base import Detection, TrackState


# COCO 17 Keypoint skeleton connections
SKELETON_PAIRS = [
    (0, 1), (0, 2), (1, 3), (2, 4),        # Facial contours
    (5, 6),                                # Shoulders
    (5, 7), (7, 9),                        # Left arm
    (6, 8), (8, 10),                       # Right arm
    (5, 11), (6, 12),                      # Torso
    (11, 12),                              # Hips
    (11, 13), (13, 15),                    # Left leg
    (12, 14), (14, 16),                    # Right leg
]


def draw_annotations(
    frame: np.ndarray,
    tracks: Dict[int, TrackState],
    active_detection: Optional[Detection] = None,
    camera_name: str = "Camera Feed",
    fps: float = 15.0
) -> np.ndarray:
    """Draws security control overlay: bounding boxes, skeleton keypoints,
    track tags, camera name, and incident banner if active.
    NO FACIAL RECOGNITION - only anonymous stick skeleton and bounding boxes.
    """
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    is_alert = active_detection is not None
    alert_track_ids = set(active_detection.track_ids) if active_detection else set()

    # Draw person tracks and skeletons
    for track_id, track in tracks.items():
        in_incident = track_id in alert_track_ids
        color_box = (68, 68, 239) if in_incident else (238, 211, 34)  # BGR: Red if alert, Cyan if normal
        box_thickness = 2 if not in_incident else 3

        x1, y1, x2, y2 = [int(v) for v in track.bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        # Draw bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color_box, box_thickness)

        # Draw Track ID label badge (no identity, purely numerical track ID)
        label = f"TRACK #{track_id}"
        if in_incident:
            label += " [FLAGGED]"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(annotated, (x1, max(0, y1 - lh - 6)), (x1 + lw + 8, y1), color_box, -1)
        cv2.putText(
            annotated,
            label,
            (x1 + 4, max(lh + 2, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (10, 15, 25),
            1,
            cv2.LINE_AA,
        )

        # Draw pose skeleton keypoints if available
        if track.keypoints is not None:
            kp = track.keypoints
            # Draw joints
            for i in range(len(kp)):
                conf = kp[i, 2] if kp.shape[1] > 2 else 1.0
                if conf > 0.35:
                    kx, ky = int(kp[i, 0]), int(kp[i, 1])
                    if 0 <= kx < w and 0 <= ky < h:
                        cv2.circle(annotated, (kx, ky), 3, (0, 255, 255) if in_incident else (34, 211, 238), -1)

            # Draw skeleton bones
            for p1, p2 in SKELETON_PAIRS:
                if p1 < len(kp) and p2 < len(kp):
                    c1 = kp[p1, 2] if kp.shape[1] > 2 else 1.0
                    c2 = kp[p2, 2] if kp.shape[1] > 2 else 1.0
                    if c1 > 0.35 and c2 > 0.35:
                        pt1 = (int(kp[p1, 0]), int(kp[p1, 1]))
                        pt2 = (int(kp[p2, 0]), int(kp[p2, 1]))
                        bone_color = (0, 165, 255) if in_incident else (220, 200, 50)
                        cv2.line(annotated, pt1, pt2, bone_color, 1, cv2.LINE_AA)

    # Top banner bar
    overlay_bar = annotated.copy()
    cv2.rectangle(overlay_bar, (0, 0), (w, 38), (14, 22, 38), -1)
    cv2.addWeighted(overlay_bar, 0.75, annotated, 0.25, 0, annotated)

    # Top camera info
    cam_text = f"CAM: {camera_name.upper()} | {fps:.0f} FPS | PRIVACY MODE: ANONYMOUS"
    cv2.putText(annotated, cam_text, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 230, 245), 1, cv2.LINE_AA)

    # Live indicator dot
    cv2.circle(annotated, (w - 75, 19), 5, (0, 0, 255), -1)
    cv2.putText(annotated, "LIVE", (w - 62, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2, cv2.LINE_AA)

    # Incident Alert banner if active
    if active_detection:
        banner = annotated.copy()
        cv2.rectangle(banner, (0, 40), (w, 85), (0, 0, 180), -1)
        cv2.addWeighted(banner, 0.85, annotated, 0.15, 0, annotated)

        type_str = active_detection.incident_type.replace("_", " ").upper()
        verif = active_detection.verification
        msg = f"! ALERT: {type_str} | CONF: {int(active_detection.confidence * 100)}% | VERIFIED {verif.get('frames_confirmed')}/{verif.get('frames_required')} FRAMES"
        cv2.putText(annotated, msg, (15, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    return annotated


@dataclass
class PendingClipRequest:
    incident_id: str
    clips_dir: str
    trigger_time: float
    start_time: float
    end_time: float
    target_fps: float


class CameraRingBuffer:
    """Maintains a sliding ring buffer of recent frames and generates evidence snapshots and clips.
    Supports pre-roll and post-roll video evidence capture around verified incidents.
    """

    def __init__(self, camera_id: str, target_fps: float = 15.0, buffer_seconds: float = 10.0):
        self.camera_id = camera_id
        self.target_fps = target_fps
        self.max_frames = int(target_fps * buffer_seconds)
        self.buffer: deque[Tuple[float, np.ndarray, np.ndarray]] = deque(maxlen=self.max_frames)
        self.pending_clips: Dict[str, PendingClipRequest] = {}
        self._lock = threading.Lock()

    def add_frame(self, timestamp: float, raw_frame: np.ndarray, annotated_frame: np.ndarray):
        """Appends a new frame to the sliding ring buffer."""
        self.buffer.append((timestamp, raw_frame.copy(), annotated_frame.copy()))

    def save_snapshot(
        self,
        incident_id: str,
        snapshots_dir: str = "./media/snapshots",
        frame: Optional[np.ndarray] = None
    ) -> str:
        """Saves verified incident frame as JPEG. Uses passed frame or latest buffer frame."""
        os.makedirs(snapshots_dir, exist_ok=True)
        filename = f"{incident_id}.jpg"
        filepath = os.path.join(snapshots_dir, filename)

        target_frame = None
        if frame is not None:
            target_frame = frame
        elif self.buffer:
            _, _, target_frame = self.buffer[-1]

        if target_frame is not None:
            cv2.imwrite(filepath, target_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        else:
            # Fallback blank frame
            blank = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(blank, f"INCIDENT: {incident_id}", (50, 360), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
            cv2.imwrite(filepath, blank)

        return f"/media/snapshots/{filename}"

    def request_clip(
        self,
        incident_id: str,
        clips_dir: str = "./media/clips",
        pre_seconds: float = 3.0,
        post_seconds: float = 3.0,
        trigger_time: Optional[float] = None
    ) -> str:
        """Schedules asynchronous clip capture preserving ~pre_seconds of pre-roll footage
        and continuing frame collection until ~post_seconds after trigger_time.
        """
        if trigger_time is None:
            trigger_time = self.buffer[-1][0] if self.buffer else time.time()

        start_time = trigger_time - pre_seconds
        end_time = trigger_time + post_seconds

        req = PendingClipRequest(
            incident_id=incident_id,
            clips_dir=clips_dir,
            trigger_time=trigger_time,
            start_time=start_time,
            end_time=end_time,
            target_fps=self.target_fps
        )
        with self._lock:
            self.pending_clips[incident_id] = req

        return f"/media/clips/{incident_id}.mp4"

    def check_pending_clips(self, current_time: Optional[float] = None) -> List[str]:
        """Checks if any active clip recordings have reached their post-incident duration.
        Dispatches writing to a background worker without blocking camera processing.
        """
        if current_time is None:
            current_time = self.buffer[-1][0] if self.buffer else time.time()

        completed: List[PendingClipRequest] = []
        with self._lock:
            for inc_id, req in list(self.pending_clips.items()):
                if current_time >= req.end_time:
                    completed.append(req)
                    del self.pending_clips[inc_id]

        finalized_ids: List[str] = []
        for req in completed:
            clip_frames = [
                ann.copy() for (t, _, ann) in self.buffer
                if req.start_time <= t <= req.end_time
            ]
            if not clip_frames and self.buffer:
                clip_frames = [ann.copy() for (_, _, ann) in list(self.buffer)[-int(self.target_fps * 6):]]

            if clip_frames:
                self._dispatch_write_clip(req.incident_id, req.clips_dir, clip_frames, req.target_fps)
                finalized_ids.append(req.incident_id)

        return finalized_ids

    def flush_pending_clips(self) -> List[str]:
        """Finalizes all outstanding pending clips immediately (e.g. on shutdown)."""
        with self._lock:
            pending_list = list(self.pending_clips.values())
            self.pending_clips.clear()

        finalized_ids: List[str] = []
        for req in pending_list:
            clip_frames = [
                ann.copy() for (t, _, ann) in self.buffer
                if t >= req.start_time
            ]
            if not clip_frames and self.buffer:
                clip_frames = [ann.copy() for (_, _, ann) in self.buffer]

            if clip_frames:
                self._dispatch_write_clip(req.incident_id, req.clips_dir, clip_frames, req.target_fps)
                finalized_ids.append(req.incident_id)

        return finalized_ids

    def save_clip(
        self,
        incident_id: str,
        clips_dir: str = "./media/clips",
        pre_seconds: float = 3.0,
        post_seconds: float = 3.0,
        trigger_time: Optional[float] = None
    ) -> str:
        """Synchronously saves an MP4 clip covering [trigger_time - pre_seconds, trigger_time + post_seconds]."""
        os.makedirs(clips_dir, exist_ok=True)
        filename = f"{incident_id}.mp4"
        filepath = os.path.join(clips_dir, filename)

        if not self.buffer:
            return f"/media/clips/{filename}"

        if trigger_time is None:
            trigger_time = self.buffer[-1][0]

        start_time = trigger_time - pre_seconds
        end_time = trigger_time + post_seconds

        clip_frames = [
            ann.copy() for (t, _, ann) in self.buffer
            if start_time <= t <= end_time
        ]

        if not clip_frames:
            clip_frames = [ann.copy() for (_, _, ann) in list(self.buffer)[-int(self.target_fps * 6):]]

        if not clip_frames:
            return f"/media/clips/{filename}"

        self._write_clip_to_file(filepath, clip_frames, self.target_fps)
        return f"/media/clips/{filename}"

    def _dispatch_write_clip(
        self,
        incident_id: str,
        clips_dir: str,
        frames: List[np.ndarray],
        fps: float
    ):
        """Dispatches MP4 file writing to a daemon thread."""
        os.makedirs(clips_dir, exist_ok=True)
        filepath = os.path.join(clips_dir, f"{incident_id}.mp4")
        t = threading.Thread(
            target=self._write_clip_to_file,
            args=(filepath, frames, fps),
            daemon=True,
            name=f"ClipWriter-{incident_id}"
        )
        t.start()

    @staticmethod
    def _write_clip_to_file(filepath: str, frames: List[np.ndarray], fps: float):
        """Encodes frame list to MP4 using OpenCV, transcoding with ffmpeg if available."""
        if not frames:
            return
        h, w = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(filepath, fourcc, float(fps), (w, h))
        for f in frames:
            out.write(f)
        out.release()

        if shutil.which("ffmpeg"):
            temp_path = filepath + ".tmp.mp4"
            cmd = [
                "ffmpeg", "-y", "-i", filepath,
                "-vcodec", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                temp_path
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                    os.replace(temp_path, filepath)
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
