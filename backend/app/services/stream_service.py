import logging
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def placeholder_jpeg(label: str = "NO SIGNAL") -> bytes:
    frame = np.zeros((480, 800, 3), dtype=np.uint8)
    frame[:] = (13, 22, 38)
    cv2.rectangle(frame, (30, 30), (770, 450), (45, 59, 78), 1)
    cv2.putText(frame, label, (55, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (210, 220, 228), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", frame)
    return encoded.tobytes() if ok else b""


def iter_mjpeg(camera_id: str, video_path: str | None = None):
    capture = None
    frame_hub = None
    try:
        from sentinel_ai.frame_hub import FrameHub
        frame_hub = FrameHub
    except ImportError:
        pass

    path = Path(video_path) if video_path else None
    if path and path.is_file():
        capture = cv2.VideoCapture(str(path))
    while True:
        jpeg = frame_hub.get_latest_jpeg(camera_id) if frame_hub else None
        if not jpeg and capture is not None:
            ok, frame = capture.read()
            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = capture.read()
            if ok:
                ok, encoded = cv2.imencode(".jpg", frame)
                jpeg = encoded.tobytes() if ok else None
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + (jpeg or placeholder_jpeg()) + b"\r\n"
        time.sleep(1 / 15)