"""Standalone CLI entry point for SentinelAI detection pipeline.
Usage:
  # Run standard multi-camera simulation
  python -m sentinel_ai.run --all

  # Process a specific video file (P0 requirement)
  python -m sentinel_ai.run --video part2/data/videos/cam_01_fall.mp4 --camera-id cam_01

  # Simulate an incident event without running inference (P0 requirement)
  python -m sentinel_ai.run --simulate-event --camera-id cam_01

  # Run with real-time preview window
  python -m sentinel_ai.run --video part2/data/videos/cam_01_fall.mp4 --show
"""

import argparse
import sys
import time
import cv2
import json
import os
import requests
from datetime import datetime, timezone

from sentinel_ai.frame_hub import FrameHub
from sentinel_ai.pipeline import PipelineManager, CameraWorker, VisionTracker
from sentinel_ai.detectors.base import Detection

def simulate_incident(camera_id: str, api_url: str):
    """Generates a valid mock incident event for testing purposes."""
    print(f"[SentinelAI Simulation] Generating mock incident for {camera_id}...")

    payload = {
        "event_id": f"evt_sim_{int(time.time())}",
        "deduplication_key": f"{camera_id}_SIMULATED_{int(time.time() // 60)}",
        "camera_id": camera_id,
        "department_id": "dept_demo_01",
        "location": "Demo Zone (Simulated)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incident_type": "FALL_COLLAPSE",
        "confidence": 0.85,
        "status": "SIMULATED",
        "evidence_reference": "/media/snapshots/sample_simulated.jpg",
        "detection_method": "SIMULATION_MODE",
        "detection_summary": {
            "track_ids": [999],
            "frames_confirmed": 15,
            "severity": "HIGH",
            "description": "SIMULATED: This is a test event to verify pipeline integration."
        },
        "priority": "HIGH",
        "workflow_state": "NEW",
        "requires_human_review": True
    }

    try:
        print(f"[SentinelAI Simulation] Sending payload to {api_url}...")
        token = os.getenv("INTERNAL_API_TOKEN", "local-dev-internal-token")
        response = requests.post(api_url, json=payload, timeout=5,
                                 headers={"Authorization": f"Bearer {token}"})
        print(f"[SentinelAI Simulation] Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[SentinelAI Simulation] Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="SentinelAI Standalone Detector Runner")

    # Mode Selection
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--camera", type=str, default="cam_01", help="Camera ID to run/preview from config (default: cam_01)")
    group.add_argument("--all", action="store_true", help="Run all cameras in parallel from config")
    group.add_argument("--video", type=str, help="Path to a specific video file to process")
    group.add_argument("--simulate-event", action="store_true", help="Generate a simulated incident event")

    # Options
    parser.add_argument("--camera-id", type=str, default="cam_01", help="Override camera ID for the event (default: cam_01)")
    parser.add_argument("--show", action="store_true", help="Display real-time OpenCV preview window")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000/api/internal/incidents", help="Backend API endpoint")

    args = parser.parse_args()

    if args.simulate_event:
        simulate_incident(args.camera_id, args.api_url)
        return

    print(f"[SentinelAI Runner] Starting SentinelAI Engine...")
    manager = PipelineManager.get_instance()

    if args.video:
        print(f"[SentinelAI Runner] Single Video Mode: {args.video}")

        pipeline_cfg = {
            "target_fps": 15.0,
            "api_url": args.api_url,
            "cooldown_seconds": 20.0,
            "ring_buffer_seconds": 10.0,
            "model_name": "part2/yolov8n-pose.pt",
            "device": "auto"
        }
        detectors_cfg = {"fall_collapse": {"enabled": True}, "vehicle_accident": {"enabled": True}}
        evidence_cfg = {
            "snapshots_dir": "./media/snapshots",
            "clips_dir": "./media/clips",
            "clip_pre_seconds": 3.0,
            "clip_post_seconds": 3.0
        }

        cam_cfg = {
            "id": args.camera_id,
            "name": f"Video Feed {args.camera_id}",
            "video_path": args.video,
            "location": "Custom Video Location"
        }

        worker = CameraWorker(
            camera_cfg=cam_cfg,
            pipeline_cfg=pipeline_cfg,
            detectors_cfg=detectors_cfg,
            evidence_cfg=evidence_cfg
        )
        worker.start()

        if args.show:
            window_title = f"SentinelAI Processing [{args.camera_id}]"
            cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
            print(f"[SentinelAI Runner] Showing feed. Press 'q' or ESC to exit.")
            try:
                while worker.is_alive():
                    jpeg_bytes = FrameHub.get_latest_jpeg(args.camera_id)
                    if jpeg_bytes:
                        import numpy as np
                        nparr = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                        if nparr is not None:
                            cv2.imshow(window_title, nparr)
                    if cv2.waitKey(30) & 0xFF in [ord('q'), 27]:
                        break
            except KeyboardInterrupt:
                pass
            finally:
                cv2.destroyAllWindows()
                worker.stop()
        else:
            print("[SentinelAI Runner] Processing full video. Please wait...")
            # Modified to wait until the video is actually finished
            import cv2
            cap = cv2.VideoCapture(args.video)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()

            # Approximate time to process: (Total Frames / Target FPS)
            estimated_time = total_frames / 15.0 # pipeline.py uses 15fps
            print(f"[SentinelAI Runner] Estimated processing time: {estimated_time:.2f} seconds.")

            try:
                # Wait for the worker to finish the video
                # In the current CameraWorker, the video loops.
                # To check the 'whole video' once, we monitor the elapsed time.
                time.sleep(estimated_time + 5)
                worker.stop()
            except KeyboardInterrupt:
                worker.stop()
            print("[SentinelAI Runner] Video analysis complete.")

    elif args.all:
        manager.start()
        print("[SentinelAI Runner] All configured cameras are running. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            manager.stop()

    elif args.camera:
        manager.start()
        if args.show:
            cam_id = args.camera
            window_title = f"SentinelAI Real-Time Feed [{cam_id}]"
            cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
            try:
                while True:
                    jpeg_bytes = FrameHub.get_latest_jpeg(cam_id)
                    if jpeg_bytes:
                        import numpy as np
                        nparr = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                        if nparr is not None:
                            cv2.imshow(window_title, nparr)
                    if cv2.waitKey(30) & 0xFF in [ord('q'), 27]:
                        break
            except KeyboardInterrupt:
                pass
            finally:
                cv2.destroyAllWindows()
                manager.stop()
        else:
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                manager.stop()

    print("[SentinelAI Runner] Exited cleanly.")

if __name__ == "__main__":
    main()
