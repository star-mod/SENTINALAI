from pathlib import Path
import cv2

video_dir = Path("part2/data/videos")

for path in sorted(video_dir.glob("*.mp4")):
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        print(f"Could not open: {path.name}")
        continue

    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frames / fps if fps > 0 else 0

    print(
        f"{path.name}: "
        f"{duration:.1f} seconds, "
        f"{fps:.2f} FPS, "
        f"{int(frames)} frames"
    )

    cap.release()