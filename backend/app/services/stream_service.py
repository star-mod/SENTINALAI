import logging
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

STREAM_FPS = float(os.getenv("STREAM_FPS", "10"))
STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", "640"))
STREAM_JPEG_QUALITY = int(os.getenv("STREAM_JPEG_QUALITY", "65"))
IDLE_STOP_SECONDS = 10.0


def placeholder_jpeg(label: str = "NO SIGNAL") -> bytes:
    frame = np.zeros((480, 800, 3), dtype=np.uint8)
    frame[:] = (13, 22, 38)
    cv2.rectangle(frame, (30, 30), (770, 450), (45, 59, 78), 1)
    cv2.putText(frame, label, (55, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (210, 220, 228), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", frame)
    return encoded.tobytes() if ok else b""


class _CameraFeed:
    """One shared decoder per camera. All viewers receive the same latest JPEG."""

    def __init__(self, camera_id: str, video_path: str | None):
        self.camera_id = camera_id
        self.video_path = video_path
        self.jpeg: bytes | None = None
        self.last_viewer = time.time()
        self.running = False
        self.lock = threading.Lock()

    def touch(self) -> None:
        self.last_viewer = time.time()
        with self.lock:
            if not self.running:
                self.running = True
                threading.Thread(target=self._run, daemon=True, name=f"feed-{self.camera_id}").start()

    def _run(self) -> None:
        capture = None
        try:
            path = Path(self.video_path) if self.video_path else None
            if path and path.is_file():
                capture = cv2.VideoCapture(str(path))
            interval = 1.0 / STREAM_FPS
            while time.time() - self.last_viewer < IDLE_STOP_SECONDS:
                started = time.time()
                jpeg = None
                if capture is not None:
                    ok, frame = capture.read()
                    if not ok:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, frame = capture.read()
                    if ok:
                        height, width = frame.shape[:2]
                        if width > STREAM_WIDTH:
                            frame = cv2.resize(frame, (STREAM_WIDTH, int(height * STREAM_WIDTH / width)), interpolation=cv2.INTER_AREA)
                        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY])
                        jpeg = encoded.tobytes() if ok else None
                self.jpeg = jpeg
                time.sleep(max(0.0, interval - (time.time() - started)))
        except Exception:
            logger.exception("Camera feed %s stopped", self.camera_id)
        finally:
            if capture is not None:
                capture.release()
            with self.lock:
                self.running = False


_feeds: dict[str, _CameraFeed] = {}
_feeds_lock = threading.Lock()


def _feed_for(camera_id: str, video_path: str | None) -> _CameraFeed:
    with _feeds_lock:
        feed = _feeds.get(camera_id)
        if feed is None or feed.video_path != video_path:
            feed = _CameraFeed(camera_id, video_path)
            _feeds[camera_id] = feed
        return feed


def iter_mjpeg(camera_id: str, video_path: str | None = None):
    frame_hub = None
    try:
        from sentinel_ai.frame_hub import FrameHub
        frame_hub = FrameHub
    except ImportError:
        pass

    feed = _feed_for(camera_id, video_path)
    placeholder = placeholder_jpeg()
    last_sent = None
    while True:
        jpeg = frame_hub.get_latest_jpeg(camera_id) if frame_hub else None
        if not jpeg:
            feed.touch()
            jpeg = feed.jpeg
        if jpeg is None:
            jpeg = placeholder
        if jpeg is not last_sent:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            last_sent = jpeg
        time.sleep(1.0 / STREAM_FPS / 2)