"""Standalone CLI entry point for SentinelAI detection pipeline.
Usage:
  python -m sentinel_ai.run --camera cam_01 --show
  python -m sentinel_ai.run --all
"""

import argparse
import sys
import time
import cv2

from sentinel_ai.frame_hub import FrameHub
from sentinel_ai.pipeline import PipelineManager


def main():
    parser = argparse.ArgumentParser(description="SentinelAI Standalone Detector Runner")
    parser.add_argument("--camera", type=str, default="cam_01", help="Camera ID to run/preview (default: cam_01)")
    parser.add_argument("--show", action="store_true", help="Display real-time OpenCV preview window")
    parser.add_argument("--all", action="store_true", help="Run all cameras in parallel")
    args = parser.parse_args()

    print(f"[SentinelAI Runner] Starting SentinelAI Engine...")
    manager = PipelineManager.get_instance()
    manager.start()

    if args.show:
        cam_id = args.camera
        window_title = f"SentinelAI Real-Time Feed [{cam_id}]"
        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
        print(f"[SentinelAI Runner] Showing feed for {cam_id}. Press 'q' or ESC in window to exit.")

        try:
            while True:
                jpeg_bytes = FrameHub.get_latest_jpeg(cam_id)
                if jpeg_bytes:
                    nparr = cv2.imdecode(cv2.imdecode(jpeg_bytes, cv2.IMREAD_COLOR), cv2.IMREAD_COLOR) if False else None
                    # Use cv2.imdecode directly on numpy byte buffer
                    import numpy as np
                    nparr = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
                    if nparr is not None:
                        cv2.imshow(window_title, nparr)
                
                key = cv2.waitKey(30) & 0xFF
                if key == ord('q') or key == 27:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()
            manager.stop()
    else:
        print("[SentinelAI Runner] Running in background. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            manager.stop()

    print("[SentinelAI Runner] Exited cleanly.")


if __name__ == "__main__":
    main()
