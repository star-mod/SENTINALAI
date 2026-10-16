"""Synthetic CCTV Feed Generator for SentinelAI Demo.
Generates 4 realistic CCTV scenario videos offline without requiring any external downloads:
  1. cam_01_fall.mp4        - Person walking, then sudden collapse/fall and stillness.
  2. cam_02_altercation.mp4 - Two people approaching and entering into physical fight.
  3. cam_03_crowd.mp4       - Crowd walking calmly, then sudden rapid panic surge/dispersion.
  4. cam_04_normal.mp4      - Normal pedestrians strolling calmly (negative control, no alert).
"""

import math
import os
import cv2
import numpy as np


WIDTH, HEIGHT = 960, 540
FPS = 15
DURATION_SEC = 12
TOTAL_FRAMES = FPS * DURATION_SEC


def draw_cctv_background(scene_name: str) -> np.ndarray:
    """Creates a realistic surveillance camera perspective background."""
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    # Slate concrete / urban ground
    img[:] = (35, 40, 48)

    # Floor perspective tiles / pavement
    for y in range(220, HEIGHT, 30):
        cv2.line(img, (0, y), (WIDTH, y), (45, 52, 62), 1)
    for x in range(0, WIDTH, 80):
        # Vanishing perspective lines towards horizon y=200
        cv2.line(img, (x, HEIGHT), (int(WIDTH / 2 + (x - WIDTH / 2) * 0.4), 200), (45, 52, 62), 1)

    # Horizon / wall
    cv2.rectangle(img, (0, 0), (WIDTH, 200), (22, 28, 36), -1)

    # Architectural features / pillars / doors
    for px in [120, 340, 620, 840]:
        cv2.rectangle(img, (px - 15, 60), (px + 15, 230), (55, 65, 78), -1)
        cv2.rectangle(img, (px - 18, 60), (px + 18, 70), (70, 82, 98), -1)

    # Bench / planter at the side
    cv2.rectangle(img, (40, 320), (160, 350), (40, 48, 58), -1)

    # Surveillance watermark info
    cv2.putText(img, f"REC [CAM-SEC] {scene_name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 120, 140), 1)
    return img


def draw_person_silhouette(
    img: np.ndarray,
    x: float,
    y: float,
    scale: float = 1.0,
    pose: str = "standing",
    arms_state: str = "normal",
    color: tuple = (200, 210, 220),
    anim_phase: float = 0.0
):
    """Draws a human figure with clear human proportions and body segments
    that YOLO and our detectors can recognize cleanly.
    """
    ix, iy = int(x), int(y)
    h_torso = int(45 * scale)
    w_shoulder = int(18 * scale)
    r_head = int(10 * scale)

    if pose == "standing":
        # Head
        cv2.circle(img, (ix, iy - h_torso - r_head), r_head, color, -1)
        # Torso
        cv2.line(img, (ix, iy - h_torso), (ix, iy - int(h_torso * 0.3)), color, max(int(6 * scale), 2))
        # Shoulders
        cv2.line(img, (ix - w_shoulder, iy - int(h_torso * 0.9)), (ix + w_shoulder, iy - int(h_torso * 0.9)), color, max(int(4 * scale), 2))

        # Arms
        sh_y = iy - int(h_torso * 0.9)
        if arms_state == "normal":
            # Walking swing
            swing = math.sin(anim_phase) * 12 * scale
            cv2.line(img, (ix - w_shoulder, sh_y), (ix - w_shoulder - int(swing * 0.5), sh_y + int(24 * scale) + int(swing)), color, 3)
            cv2.line(img, (ix + w_shoulder, sh_y), (ix + w_shoulder + int(swing * 0.5), sh_y + int(24 * scale) - int(swing)), color, 3)
        elif arms_state == "fighting":
            # Agitated rapid striking motion
            punch = math.sin(anim_phase * 4.0) * 22 * scale
            cv2.line(img, (ix - w_shoulder, sh_y), (ix - w_shoulder + int(punch), sh_y - int(8 * scale)), color, 4)
            cv2.line(img, (ix + w_shoulder, sh_y), (ix + w_shoulder - int(punch), sh_y + int(5 * scale)), color, 4)

        # Legs (walking stride)
        stride = math.sin(anim_phase) * 15 * scale
        hip_y = iy - int(h_torso * 0.3)
        cv2.line(img, (ix - int(8 * scale), hip_y), (ix - int(stride), iy), color, max(int(4 * scale), 2))
        cv2.line(img, (ix + int(8 * scale), hip_y), (ix + int(stride), iy), color, max(int(4 * scale), 2))

    elif pose == "falling":
        # Mid-air pitch forward/downward
        angle = anim_phase  # 0 to pi/2
        cv2.circle(img, (ix + int(25 * math.sin(angle)), iy - int(h_torso * math.cos(angle))), r_head, color, -1)
        cv2.line(img, (ix, iy - int(10 * scale)), (ix + int(20 * math.sin(angle)), iy - int(h_torso * math.cos(angle))), color, 4)

    elif pose == "fallen":
        # Prone horizontal body on ground
        # Head on ground
        cv2.circle(img, (ix - int(35 * scale), iy - int(6 * scale)), r_head, color, -1)
        # Horizontal torso
        cv2.line(img, (ix - int(30 * scale), iy - int(6 * scale)), (ix + int(25 * scale), iy - int(6 * scale)), color, max(int(7 * scale), 3))
        # Legs extended
        cv2.line(img, (ix + int(25 * scale), iy - int(6 * scale)), (ix + int(50 * scale), iy - int(4 * scale)), color, max(int(4 * scale), 2))


def generate_fall_video(output_path: str):
    """Generates cam_01: Fall and Collapse Scenario."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, float(FPS), (WIDTH, HEIGHT))

    x = 180.0
    y = 380.0
    bg = draw_cctv_background("Central Plaza - North")

    for f in range(TOTAL_FRAMES):
        t = f / FPS
        frame = bg.copy()
        timestamp_str = f"2026-10-09 14:22:{int(t):02d}.{int((t%1)*100):02d}"
        cv2.putText(frame, timestamp_str, (WIDTH - 240, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1)

        # Background pedestrian 1 (walking calmly in distance)
        bg1_x = 750 - (f * 1.5) % 800
        draw_person_silhouette(frame, bg1_x, 260, scale=0.7, pose="standing", anim_phase=f * 0.4, color=(160, 170, 180))

        if t < 4.0:
            # Walking steadily
            x += 2.2
            anim = f * 0.5
            draw_person_silhouette(frame, x, y, scale=1.1, pose="standing", arms_state="normal", anim_phase=anim)
        elif t < 4.8:
            # Collapse phase: rapid drop and rotation
            phase = (t - 4.0) / 0.8
            drop_y = y + (phase * 15)
            draw_person_silhouette(frame, x + (phase * 20), drop_y, scale=1.1, pose="falling", anim_phase=phase * (math.pi / 2))
        else:
            # Person is collapsed on ground and still
            draw_person_silhouette(frame, x + 25, y + 15, scale=1.1, pose="fallen", anim_phase=0.0)

        out.write(frame)

    out.release()
    print(f"Generated {output_path}")


def generate_altercation_video(output_path: str):
    """Generates cam_02: Physical Altercation Scenario."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, float(FPS), (WIDTH, HEIGHT))

    x1, y1 = 340.0, 370.0
    x2, y2 = 600.0, 370.0
    bg = draw_cctv_background("Metro Transit Hub - East Concourse")

    for f in range(TOTAL_FRAMES):
        t = f / FPS
        frame = bg.copy()
        timestamp_str = f"2026-10-09 14:24:{int(t):02d}.{int((t%1)*100):02d}"
        cv2.putText(frame, timestamp_str, (WIDTH - 240, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1)

        # Distant pedestrian
        draw_person_silhouette(frame, 150 + (f * 1.0) % 700, 250, scale=0.65, pose="standing", anim_phase=f * 0.4, color=(150, 160, 170))

        if t < 3.5:
            # Approaching each other
            x1 += 2.0
            x2 -= 2.0
            draw_person_silhouette(frame, x1, y1, scale=1.05, pose="standing", arms_state="normal", anim_phase=f * 0.4)
            draw_person_silhouette(frame, x2, y2, scale=1.05, pose="standing", arms_state="normal", anim_phase=f * 0.4 + 1.5)
        else:
            # In close proximity with rapid aggressive altercation motion
            jitter1 = math.sin(f * 2.0) * 5
            jitter2 = math.cos(f * 2.0) * 5
            draw_person_silhouette(frame, 440 + jitter1, y1, scale=1.05, pose="standing", arms_state="fighting", anim_phase=f * 0.8)
            draw_person_silhouette(frame, 480 + jitter2, y2, scale=1.05, pose="standing", arms_state="fighting", anim_phase=f * 0.8 + 2.0)

        out.write(frame)

    out.release()
    print(f"Generated {output_path}")


def generate_crowd_video(output_path: str):
    """Generates cam_03: Abnormal Crowd Surge / Panic Scenario."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, float(FPS), (WIDTH, HEIGHT))

    bg = draw_cctv_background("Stadium Gate 4 - Entry Plaza")
    # Initial positions of 8 people in crowd
    crowd = [
        {"x": 420.0, "y": 340.0, "vx": 0.8, "vy": 0.2, "scale": 0.95},
        {"x": 460.0, "y": 360.0, "vx": 0.9, "vy": -0.1, "scale": 1.0},
        {"x": 390.0, "y": 380.0, "vx": 0.7, "vy": 0.1, "scale": 1.05},
        {"x": 510.0, "y": 330.0, "vx": 0.6, "vy": 0.3, "scale": 0.9},
        {"x": 480.0, "y": 400.0, "vx": 0.85, "vy": -0.2, "scale": 1.1},
        {"x": 350.0, "y": 350.0, "vx": 0.75, "vy": 0.15, "scale": 0.95},
        {"x": 540.0, "y": 370.0, "vx": 0.65, "vy": 0.1, "scale": 1.0},
        {"x": 410.0, "y": 420.0, "vx": 0.8, "vy": -0.1, "scale": 1.15},
    ]

    for f in range(TOTAL_FRAMES):
        t = f / FPS
        frame = bg.copy()
        timestamp_str = f"2026-10-09 14:26:{int(t):02d}.{int((t%1)*100):02d}"
        cv2.putText(frame, timestamp_str, (WIDTH - 240, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1)

        is_panic = t >= 4.0

        for idx, p in enumerate(crowd):
            if not is_panic:
                # Steady walking group
                p["x"] += p["vx"] * 1.5
                p["y"] += p["vy"] * 1.5
                anim = f * 0.4 + idx
                draw_person_silhouette(frame, p["x"], p["y"], scale=p["scale"], pose="standing", anim_phase=anim)
            else:
                # Rapid divergent stampede / scatter
                # Direction diverges outwards from center (450, 360)
                dx = p["x"] - 450.0
                dy = p["y"] - 360.0
                norm = max(math.hypot(dx, dy), 1.0)
                # High speed surge
                p["x"] += (dx / norm) * 7.5
                p["y"] += (dy / norm) * 4.5
                anim = f * 1.2 + idx
                draw_person_silhouette(frame, p["x"], p["y"], scale=p["scale"], pose="standing", arms_state="normal", anim_phase=anim)

        out.write(frame)

    out.release()
    print(f"Generated {output_path}")


def generate_normal_video(output_path: str):
    """Generates cam_04: Normal Pedestrians (Negative Control)."""
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, float(FPS), (WIDTH, HEIGHT))

    bg = draw_cctv_background("Financial District - Main Arcade")
    peds = [
        {"x": 100.0, "y": 380.0, "speed": 1.8, "scale": 1.05},
        {"x": 800.0, "y": 360.0, "speed": -1.6, "scale": 1.0},
        {"x": 300.0, "y": 280.0, "speed": 1.2, "scale": 0.75},
        {"x": 650.0, "y": 290.0, "speed": -1.3, "scale": 0.8},
    ]

    for f in range(TOTAL_FRAMES):
        t = f / FPS
        frame = bg.copy()
        timestamp_str = f"2026-10-09 14:28:{int(t):02d}.{int((t%1)*100):02d}"
        cv2.putText(frame, timestamp_str, (WIDTH - 240, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 180, 200), 1)

        for idx, p in enumerate(peds):
            p["x"] += p["speed"]
            # Wrap around
            if p["speed"] > 0 and p["x"] > WIDTH + 50:
                p["x"] = -30.0
            elif p["speed"] < 0 and p["x"] < -50:
                p["x"] = WIDTH + 30.0

            anim = f * 0.4 + idx
            draw_person_silhouette(frame, p["x"], p["y"], scale=p["scale"], pose="standing", anim_phase=anim)

        out.write(frame)

    out.release()
    print(f"Generated {output_path}")


def generate_all_samples(output_dir: str = "./data/videos"):
    os.makedirs(output_dir, exist_ok=True)
    generate_fall_video(os.path.join(output_dir, "cam_01_fall.mp4"))
    generate_altercation_video(os.path.join(output_dir, "cam_02_altercation.mp4"))
    generate_crowd_video(os.path.join(output_dir, "cam_03_crowd.mp4"))
    generate_normal_video(os.path.join(output_dir, "cam_04_normal.mp4"))


if __name__ == "__main__":
    generate_all_samples()
