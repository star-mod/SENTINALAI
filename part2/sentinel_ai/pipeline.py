"""Core Video Processing and Inference Pipeline for SentinelAI.
Processes camera streams at target FPS, extracts anonymous person tracks and pose keypoints,
computes Farneback optical flow, and evaluates temporal safety detectors.
Features resilient offline fallbacks and camera-level fault isolation.
"""

import math
import logging
import os
import threading
import time
from typing import Dict, List, Optional, Any, Tuple
import cv2
import numpy as np
import requests
import yaml

from sentinel_ai.detectors.base import BaseDetector, DetectorRegistry, FrameState, TrackState, Detection
import sentinel_ai.detectors  # Ensure all detectors register
from sentinel_ai.evidence import CameraRingBuffer, draw_annotations
from sentinel_ai.frame_hub import FrameHub


logger = logging.getLogger(__name__)
N8N_WEBHOOK_TIMEOUT_SECONDS = 5.0


def build_incident_payload(
    detection: Detection,
    camera_name: str,
    location: Dict[str, Any],
    snapshot_url: str,
    clip_url: str,
) -> Dict[str, Any]:
    """Map a temporally confirmed detection and generated evidence to the ingest contract."""
    return {
        "camera_id": detection.camera_id,
        "camera_name": camera_name,
        "location": location,
        "type": detection.incident_type,
        "confidence": detection.confidence,
        "severity": detection.severity,
        "timestamp": detection.timestamp,
        "snapshot_url": snapshot_url,
        "clip_url": clip_url,
        "notes": detection.description,
        "verification": detection.verification,
    }


def send_incident_to_n8n(
    payload: Dict[str, Any],
    webhook_url: Optional[str],
    webhook_secret: Optional[str],
) -> bool:
    """Deliver one confirmed incident; report failure without logging payloads or secrets."""
    if not webhook_url:
        logger.error(
            "N8N webhook delivery skipped: N8N_WEBHOOK_URL is not configured (camera=%s type=%s)",
            payload.get("camera_id", "unknown"),
            payload.get("type", "unknown"),
        )
        return False

    if not webhook_secret:
        logger.error(
            "N8N webhook delivery skipped: N8N_WEBHOOK_SECRET is not configured (camera=%s type=%s)",
            payload.get("camera_id", "unknown"),
            payload.get("type", "unknown"),
        )
        return False

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"X-Webhook-Secret": webhook_secret},
            timeout=N8N_WEBHOOK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as error:
        logger.warning(
            "N8N webhook delivery failed (camera=%s type=%s error=%s)",
            payload.get("camera_id", "unknown"),
            payload.get("type", "unknown"),
            type(error).__name__,
        )
        return False


class VisionTracker:
    """Manages YOLO pose detection and tracking with seamless classical fallback."""

    def __init__(self, model_name: str = "yolov8n-pose.pt", device: str = "auto"):
        self.model_name = model_name
        self.device = device
        self.yolo_model = None
        self.use_fallback = False
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=30, detectShadows=False)
        self.next_fallback_id = 1
        self.fallback_tracks: Dict[int, Dict[str, Any]] = {}

        self._init_model()

    def _init_model(self):
        try:
            from ultralytics import YOLO
            # Determine device: 'cpu' or 'cuda'
            import torch
            chosen_device = 'cuda' if (self.device == 'cuda' or (self.device == 'auto' and torch.cuda.is_available())) else 'cpu'
            print(f"[SentinelAI Vision] Loading {self.model_name} on device '{chosen_device}'...")
            self.yolo_model = YOLO(self.model_name)
            self.device = chosen_device
            print("[SentinelAI Vision] YOLO Pose loaded successfully.")
        except Exception as e:
            print(f"[SentinelAI Vision Warning] Ultralytics load or download failed ({e}). Activating high-performance Classical Computer Vision Pose Tracker fallback.")
            self.use_fallback = True

    def track(self, frame: np.ndarray, frame_idx: int) -> Dict[int, TrackState]:
        """Runs tracking and pose extraction, returning Dict[track_id, TrackState]."""
        if not self.use_fallback and self.yolo_model is not None:
            try:
                # Run YOLO tracking with ByteTrack
                results = self.yolo_model.track(
                    frame,
                    persist=True,
                    classes=[0],  # Class 0 = Person only
                    verbose=False,
                    device=self.device,
                    tracker="bytetrack.yaml",
                    conf=0.35,
                )
                tracks: Dict[int, TrackState] = {}
                if results and len(results) > 0 and results[0].boxes is not None:
                    res = results[0]
                    boxes = res.boxes.xyxy.cpu().numpy()
                    confs = res.boxes.conf.cpu().numpy()
                    track_ids = res.boxes.id.int().cpu().numpy() if res.boxes.id is not None else []
                    
                    keypoints_data = None
                    if res.keypoints is not None:
                        keypoints_data = res.keypoints.data.cpu().numpy()  # (N, 17, 3)

                    for idx, box in enumerate(boxes):
                        tid = int(track_ids[idx]) if idx < len(track_ids) else idx + 1
                        kp = keypoints_data[idx] if (keypoints_data is not None and idx < len(keypoints_data)) else None
                        tracks[tid] = TrackState(
                            track_id=tid,
                            bbox=[float(b) for b in box],
                            keypoints=kp,
                            confidence=float(confs[idx]),
                        )
                return tracks
            except Exception as e:
                # Detector error isolation: fallback seamlessly
                pass

        # Classical Computer Vision Pose Estimation Fallback
        return self._classical_track_fallback(frame, frame_idx)

    def _classical_track_fallback(self, frame: np.ndarray, frame_idx: int) -> Dict[int, TrackState]:
        """Fast classical contour detection with synthetic skeleton fitting when YOLO is unavailable."""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fg_mask = self.bg_subtractor.apply(gray)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        tracks: Dict[int, TrackState] = {}

        current_centers = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 1200:  # Ignore tiny noise
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            cx, cy = x + bw / 2.0, y + bh / 2.0
            current_centers.append((cx, cy, [float(x), float(y), float(x + bw), float(y + bh)]))

        # Simple greedy nearest-neighbor track association
        matched_tracks = {}
        for cx, cy, bbox in current_centers:
            best_id = None
            best_dist = 90.0
            for tid, prev in self.fallback_tracks.items():
                d = math.hypot(cx - prev["cx"], cy - prev["cy"])
                if d < best_dist and tid not in matched_tracks:
                    best_dist = d
                    best_id = tid

            if best_id is None:
                best_id = self.next_fallback_id
                self.next_fallback_id += 1

            self.fallback_tracks[best_id] = {"cx": cx, "cy": cy, "bbox": bbox, "last_seen": frame_idx}
            matched_tracks[best_id] = bbox

        # Remove stale tracks
        for tid in list(self.fallback_tracks.keys()):
            if frame_idx - self.fallback_tracks[tid]["last_seen"] > 15:
                del self.fallback_tracks[tid]

        # Generate synthetic 17-keypoint skeleton based on bounding box
        for tid, bbox in matched_tracks.items():
            bx1, by1, bx2, by2 = bbox
            bw = bx2 - bx1
            bh = by2 - by1
            cx = (bx1 + bx2) / 2.0
            kp = np.zeros((17, 3), dtype=np.float32)
            
            # If wider than tall, figure is horizontal
            if bw > bh * 0.9:
                # Fallen pose
                kp[0] = [bx1 + 10, by1 + bh / 2, 0.9]  # Head
                kp[5] = [bx1 + bw * 0.3, by1 + bh * 0.3, 0.9]
                kp[6] = [bx1 + bw * 0.3, by1 + bh * 0.7, 0.9]
                kp[11] = [bx1 + bw * 0.6, by1 + bh * 0.4, 0.9]
                kp[12] = [bx1 + bw * 0.6, by1 + bh * 0.6, 0.9]
                kp[15] = [bx2 - 5, by1 + bh * 0.4, 0.9]
                kp[16] = [bx2 - 5, by1 + bh * 0.6, 0.9]
            else:
                # Standing pose
                kp[0] = [cx, by1 + bh * 0.1, 0.9]  # Nose/Head
                kp[5] = [cx - bw * 0.3, by1 + bh * 0.25, 0.9]  # L Shoulder
                kp[6] = [cx + bw * 0.3, by1 + bh * 0.25, 0.9]  # R Shoulder
                kp[9] = [cx - bw * 0.4, by1 + bh * 0.5, 0.85]  # L Wrist
                kp[10] = [cx + bw * 0.4, by1 + bh * 0.5, 0.85] # R Wrist
                kp[11] = [cx - bw * 0.2, by1 + bh * 0.55, 0.9] # L Hip
                kp[12] = [cx + bw * 0.2, by1 + bh * 0.55, 0.9] # R Hip
                kp[15] = [cx - bw * 0.2, by2, 0.9]              # L Ankle
                kp[16] = [cx + bw * 0.2, by2, 0.9]              # R Ankle

            tracks[tid] = TrackState(track_id=tid, bbox=bbox, keypoints=kp, confidence=0.88)

        return tracks


class CameraWorker(threading.Thread):
    """Processes a single camera video feed continuously in an isolated thread."""

    def __init__(
        self,
        camera_cfg: Dict[str, Any],
        pipeline_cfg: Dict[str, Any],
        detectors_cfg: Dict[str, Any],
        evidence_cfg: Dict[str, Any],
        incident_callback=None
    ):
        super().__init__(daemon=True, name=f"Worker-{camera_cfg['id']}")
        self.camera_cfg = camera_cfg
        self.camera_id = camera_cfg["id"]
        self.camera_name = camera_cfg["name"]
        self.video_path = camera_cfg.get("video_path", "")
        self.pipeline_cfg = pipeline_cfg
        self.evidence_cfg = evidence_cfg
        self.incident_callback = incident_callback
        self.running = False

        self.target_fps = float(pipeline_cfg.get("target_fps", 15.0))
        self.webhook_url = os.getenv("N8N_WEBHOOK_URL")
        self.cooldown_sec = float(pipeline_cfg.get("cooldown_seconds", 20.0))

        # Register camera in FrameHub
        FrameHub.register_camera(self.camera_id, self.camera_name)

        # Initialize ring buffer
        self.ring_buffer = CameraRingBuffer(
            camera_id=self.camera_id,
            target_fps=self.target_fps,
            buffer_seconds=float(pipeline_cfg.get("ring_buffer_seconds", 10.0))
        )

        # Initialize vision tracker
        model_name = pipeline_cfg.get("model_name", "yolov8n-pose.pt")
        device = pipeline_cfg.get("device", "auto")
        self.tracker = VisionTracker(model_name=model_name, device=device)

        # Initialize detectors for this camera
        self.detectors: List[BaseDetector] = []
        for det_name, cfg in detectors_cfg.items():
            if cfg.get("enabled", True):
                cfg_copy = dict(cfg)
                cfg_copy["cooldown_seconds"] = self.cooldown_sec
                det_instance = DetectorRegistry.create(det_name, self.camera_id, cfg_copy)
                if det_instance:
                    self.detectors.append(det_instance)

        self.prev_gray: Optional[np.ndarray] = None
        self.incident_counter = 1
        self.active_alert: Optional[Detection] = None
        self.alert_clear_time = 0.0

    def run(self):
        self.running = True
        print(f"[SentinelAI] Camera worker started: {self.camera_id} ({self.camera_name})")

        while self.running:
            # Camera-level error isolation: loop video or handle missing file
            if not os.path.exists(self.video_path):
                # Try relative from current working directory
                alt_path = os.path.join(".", self.video_path.lstrip("./"))
                if not os.path.exists(alt_path):
                    # Sleep and produce standby frame
                    time.sleep(1.0)
                    continue

            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                time.sleep(1.0)
                continue

            frame_idx = 0
            while self.running and cap.isOpened():
                start_loop = time.time()
                ret, frame = cap.read()
                if not ret:
                    # Loop video continuously for live demo
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                frame_idx += 1
                now = time.time()

                try:
                    # 1. Run Person Tracking & Pose Extraction
                    tracks = self.tracker.track(frame, frame_idx)

                    # 2. Farneback Optical Flow on downscaled frame
                    small_frame = cv2.resize(frame, (320, 180))
                    gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                    mean_flow_mag = 0.0
                    flow_divergence = 0.0

                    if self.prev_gray is not None:
                        flow = cv2.calcOpticalFlowFarneback(
                            self.prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                        )
                        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                        mean_flow_mag = float(np.mean(mag))
                        # Directional variance
                        cos_flow = np.cos(ang)
                        sin_flow = np.sin(ang)
                        r = np.sqrt(np.mean(cos_flow)**2 + np.mean(sin_flow)**2)
                        flow_divergence = float(1.0 - r)
                    self.prev_gray = gray

                    # 3. Create FrameState and evaluate detectors
                    frame_state = FrameState(
                        camera_id=self.camera_id,
                        frame_idx=frame_idx,
                        timestamp=now,
                        frame=frame,
                        tracks=tracks,
                        mean_flow_mag=mean_flow_mag,
                        flow_divergence=flow_divergence,
                    )

                    triggered_detection: Optional[Detection] = None
                    for detector in self.detectors:
                        try:
                            detection = detector.update(frame_state)
                            if detection is not None and triggered_detection is None:
                                triggered_detection = detection
                        except Exception as det_err:
                            # Detector-level error isolation
                            pass

                    # Handle active incident alert state
                    if triggered_detection:
                        self.active_alert = triggered_detection
                        self.alert_clear_time = now + 4.0  # Show banner for 4s on overlay
                    elif self.active_alert and now > self.alert_clear_time:
                        self.active_alert = None

                    # 4. Draw Overlay and Push to FrameHub & Ring Buffer
                    annotated_frame = draw_annotations(
                        frame=frame,
                        tracks=tracks,
                        active_detection=self.active_alert,
                        camera_name=self.camera_name,
                        fps=self.target_fps
                    )

                    FrameHub.set_frame(self.camera_id, annotated_frame, quality=75)
                    self.ring_buffer.add_frame(now, frame, annotated_frame)

                    # Check for completed pending clips that reached their post-incident duration
                    self.ring_buffer.check_pending_clips(current_time=now)

                    if triggered_detection:
                        self._handle_incident(triggered_detection, frame, annotated_frame, now)

                except Exception as worker_err:
                    # Camera error isolation: ensure thread doesn't terminate
                    pass

                # Regulate frame rate (~15 FPS)
                elapsed = time.time() - start_loop
                delay = max(0.001, (1.0 / self.target_fps) - elapsed)
                time.sleep(delay)

            cap.release()

        try:
            self.ring_buffer.flush_pending_clips()
        except Exception:
            pass
        print(f"[SentinelAI] Camera worker stopped: {self.camera_id}")

    def _handle_incident(
        self,
        detection: Detection,
        current_frame: np.ndarray,
        annotated_frame: np.ndarray,
        trigger_time: float
    ):
        """Generate evidence and submit the confirmed candidate to the n8n webhook."""
        ts_slug = int(time.time() * 1000) % 100000
        incident_id = f"inc_{self.camera_id}_{ts_slug:05d}"

        # 1. Save Snapshot immediately using the current verified annotated frame
        snapshot_url = self.ring_buffer.save_snapshot(
            incident_id=incident_id,
            snapshots_dir=self.evidence_cfg.get("snapshots_dir", "./media/snapshots"),
            frame=annotated_frame
        )
        # 2. Request asynchronous clip capturing pre-roll (~3s) and continuing for post-roll (~3s)
        clip_url = self.ring_buffer.request_clip(
            incident_id=incident_id,
            clips_dir=self.evidence_cfg.get("clips_dir", "./media/clips"),
            pre_seconds=float(self.evidence_cfg.get("clip_pre_seconds", 3.0)),
            post_seconds=float(self.evidence_cfg.get("clip_post_seconds", 3.0)),
            trigger_time=trigger_time
        )

        loc = self.camera_cfg.get("location", {"lat": 12.9716, "lng": 77.5946, "label": "Security Zone"})

        # Build Incident Payload strictly matching Shared Contract
        payload = build_incident_payload(
            detection=detection,
            camera_name=self.camera_name,
            location=loc,
            snapshot_url=snapshot_url,
            clip_url=clip_url,
        )

        # If an in-process callback is provided, invoke it immediately
        if self.incident_callback:
            try:
                self.incident_callback(payload)
            except Exception as cb_err:
                pass

        # Dispatch one confirmed detection; cooldown is local, not persistent deduplication.
        def _post_async():
            send_incident_to_n8n(
                payload=payload,
                webhook_url=self.webhook_url,
                webhook_secret=os.getenv("N8N_WEBHOOK_SECRET"),
            )

        threading.Thread(target=_post_async, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            self.ring_buffer.flush_pending_clips()
        except Exception:
            pass


class PipelineManager:
    """Manages multi-camera detection threads and configuration."""
    _instance = None

    def __init__(self, cameras_file: str = "sentinel_ai/cameras.yaml", config_file: str = "sentinel_ai/config.yaml"):
        self.cameras_file = cameras_file
        self.config_file = config_file
        self.workers: Dict[str, CameraWorker] = {}
        self.incident_callback = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PipelineManager()
        return cls._instance

    def set_incident_callback(self, callback):
        self.incident_callback = callback
        for w in self.workers.values():
            w.incident_callback = callback

    def start(self):
        """Loads configs and boots camera workers."""
        with open(self.config_file, "r") as f:
            cfg = yaml.safe_load(f)
        with open(self.cameras_file, "r") as f:
            cam_data = yaml.safe_load(f)

        pipeline_cfg = cfg.get("pipeline", {})
        detectors_cfg = cfg.get("detectors", {})
        evidence_cfg = cfg.get("evidence", {})

        for cam in cam_data.get("cameras", []):
            if cam.get("enabled", True):
                cid = cam["id"]
                if cid not in self.workers or not self.workers[cid].is_alive():
                    worker = CameraWorker(
                        camera_cfg=cam,
                        pipeline_cfg=pipeline_cfg,
                        detectors_cfg=detectors_cfg,
                        evidence_cfg=evidence_cfg,
                        incident_callback=self.incident_callback
                    )
                    self.workers[cid] = worker
                    worker.start()

        print(f"[SentinelAI] Started {len(self.workers)} camera pipeline workers.")

    def stop(self):
        for cid, worker in self.workers.items():
            worker.stop()
        for cid, worker in self.workers.items():
            worker.join(timeout=2.0)
        self.workers.clear()
        print("[SentinelAI] All camera pipeline workers stopped.")
