"""FrameHub: In-memory real-time frame distribution hub for MJPEG streaming.
Provides thread-safe access to the latest encoded JPEG frames per camera.
Includes automatic standby placeholder generation when a camera is offline or buffering.
"""

import threading
import time
from typing import Dict, Optional
import cv2
import numpy as np


class FrameHub:
    """Thread-safe store for real-time video frames accessed by FastAPI MJPEG streams."""
    _lock = threading.Lock()
    _frames: Dict[str, bytes] = {}
    _timestamps: Dict[str, float] = {}
    _camera_names: Dict[str, str] = {}
    _placeholders: Dict[str, bytes] = {}

    @classmethod
    def register_camera(cls, camera_id: str, camera_name: str = "Security Camera"):
        with cls._lock:
            cls._camera_names[camera_id] = camera_name

    @classmethod
    def set_frame(cls, camera_id: str, frame: np.ndarray, quality: int = 75):
        """Encodes an OpenCV image to JPEG and stores in memory."""
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ret:
            with cls._lock:
                cls._frames[camera_id] = buffer.tobytes()
                cls._timestamps[camera_id] = time.time()

    @classmethod
    def set_jpeg(cls, camera_id: str, jpeg_bytes: bytes):
        with cls._lock:
            cls._frames[camera_id] = jpeg_bytes
            cls._timestamps[camera_id] = time.time()

    @classmethod
    def get_latest_jpeg(cls, camera_id: str) -> bytes:
        """Retrieves the latest JPEG frame for camera_id.
        If no frame exists or camera is stale (> 5s without update), returns a generated standby frame.
        """
        now = time.time()
        with cls._lock:
            last_ts = cls._timestamps.get(camera_id, 0.0)
            if camera_id in cls._frames and (now - last_ts) < 5.0:
                return cls._frames[camera_id]

        # Generate or return cached standby placeholder
        return cls._get_standby_frame(camera_id)

    @classmethod
    def _get_standby_frame(cls, camera_id: str) -> bytes:
        cam_name = cls._camera_names.get(camera_id, camera_id)
        # Create dark SOC standby card
        h, w = 480, 854
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = (14, 22, 38)  # Mission control panel background #0E1626 in BGR

        # Draw tech border and grid lines
        cv2.rectangle(img, (10, 10), (w - 10, h - 10), (50, 65, 85), 1)
        for y in range(60, h, 80):
            cv2.line(img, (20, y), (w - 20, y), (25, 35, 55), 1)

        # Header
        cv2.putText(img, f"SENTINEL-AI FEED // {cam_name.upper()}", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (34, 211, 238), 1, cv2.LINE_AA)
        
        # Center message
        status_txt = "CAMERA FEED STANDBY / INITIALIZING"
        (tw, th), _ = cv2.getTextSize(status_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(img, status_txt, ((w - tw) // 2, (h // 2) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 225, 235), 2, cv2.LINE_AA)

        sub_txt = "Connecting to RTSP / Edge Stream... Pipeline active."
        (stw, _), _ = cv2.getTextSize(sub_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.putText(img, sub_txt, ((w - stw) // 2, (h // 2) + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 160, 185), 1, cv2.LINE_AA)

        # Bottom timestamp
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        cv2.putText(img, ts_str, (30, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 120, 140), 1, cv2.LINE_AA)

        ret, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buffer.tobytes() if ret else b""
