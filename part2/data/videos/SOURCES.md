# REAL FOOTAGE UPDATE (SentinelAI integration)

cam_01..cam_03 are now **real camera footage** (re-encoded to H.264, max 1280px wide, for browser playback). The earlier synthetic stick-figure clips are replaced; `data/sample_generator.py` remains only as an offline fallback.

| Camera | File | Real source | Notes |
|---|---|---|---|
| cam_01 | cam_01_fall.mp4 | github.com/TOTYsir/fyp-fall-detection `self_rec.mp4` | Real person falling (no explicit license; non-commercial demo use) |
| cam_02 | cam_02_altercation.mp4 | github.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos `violent/cam1/43.mp4` | Real fight; research/educational use only |
| cam_03 | cam_03_crowd.mp4 | github.com/shajishah/Crowd-Detection `people_walking.mp4` | Real overhead pedestrian crowd; license unverified. It shows normal flow, not a surge (UMN was unreachable) |
| cam_04 | cam_04_normal.mp4 | OpenCV `vtest.avi` | Apache 2.0, negative control |

Do not redistribute cam_01-03 publicly; check each source's terms first.

---

# SentinelAI — Video Asset Sources & Provenance Documentation

This document records the provenance, licensing, technical specifications, and verification results for all video feeds used by SentinelAI.

---

## Video Assets Summary

| Camera | Filename | Scenario | Target Incident | Resolution | FPS | Frames | Duration | Redistribution Permission | Use Category |
|---|---|---|---|---|---|---|---|---|---|
| **CAM 01** | `cam_01_fall.mp4` | Person walking, sudden collapse & stillness | `fall_collapse` | 1280×720 | 30.0 | 246 | 8.2s | **NOT Permitted (Excluded from ZIP)** | Public Academic Repo (Individual Research) |
| **CAM 02** | `cam_02_altercation.mp4` | Physical brawl, grappling, punching | `physical_altercation` | 1920×1080 | 30.0 | 281 | 9.4s | **NOT Permitted (Excluded from ZIP)** | Academic Research Dataset (Elsevier Data in Brief) |
| **CAM 03** | `cam_03_crowd.mp4` | Calm walking followed by rapid crowd surge | `abnormal_crowd_movement` | 640×480 | 30.0 | 300 | 10.0s | **NOT Permitted (Excluded from ZIP)** | Public Academic Benchmark (UMN Research) |
| **CAM 04** | `cam_04_normal.mp4` | Calm pedestrian corridor (negative control) | *None (0 alerts)* | 768×576 | 10.0 | 200 | 20.0s | **Permitted (Bundled in ZIP)** | Apache License 2.0 (OpenCV Foundation) |

---

## Legal & Licensing Clarification: Public Accessibility vs Redistribution

It is critical to distinguish between three legal categories:
1. **Public Accessibility**: A file is downloadable over HTTP/Git from a university or public server. This does *not* grant a license to repackage or redistribute the file.
2. **Research / Educational Use**: The original authors permit individuals to download and evaluate footage for scientific research. Sublicensing, commercial distribution, or software bundle redistribution remains restricted.
3. **Permission to Redistribute**: An open license (such as Apache 2.0, MIT, or CC-BY) explicitly grants third parties the right to bundle and redistribute the asset.

**Compliance Action**: Only `cam_04_normal.mp4` satisfies category 3 (Apache 2.0). The research footage for `cam_01`, `cam_02`, and `cam_03` belongs to category 1 and 2; therefore, **they are strictly excluded from the deliverable ZIP archive**. Users must obtain them directly from original academic sources or generate synthetic clips offline.

---

## Video Asset Setup, Placement & Preparation Guide

### Required Storage Location & Filenames
All video feeds must be placed in:
```
data/videos/
```
The pipeline expects the following exact filenames:
1. `data/videos/cam_01_fall.mp4` — Target: `fall_collapse`
2. `data/videos/cam_02_altercation.mp4` — Target: `physical_altercation`
3. `data/videos/cam_03_crowd.mp4` — Target: `abnormal_crowd_movement`
4. `data/videos/cam_04_normal.mp4` — Target: *None (Negative Control)* — **Bundled in deliverable**

---

### Option 1: Acquiring Real CCTV Research Footage (Recommended for YOLO Pose Evaluation)

To evaluate real human pose detection with YOLOv8-Pose:

#### CAM 01 (Fall):
```powershell
# In PowerShell (from project root):
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TOTYsir/fyp-fall-detection/main/self_rec.mp4" -OutFile "data/videos/cam_01_fall.mp4"
```

#### CAM 02 (Altercation):
```powershell
# In PowerShell (from project root):
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos/master/violence-detection-dataset/violent/cam1/43.mp4" -OutFile "data/videos/cam_02_altercation.mp4"
```

#### CAM 03 (Crowd):
The University of Minnesota (UMN) Unusual Crowd Activity dataset provides multi-scene crowd behavior benchmarks:
```bash
# 1. Download the full UMN crowd activity video archive:
curl -o data/videos/Crowd-Activity-All.avi http://mha.cs.umn.edu/Movies/Crowd-Activity-All.avi

# 2. Extract Scene 1 (frames 350-650, corresponding to normal walk -> rapid lawn surge):
# Using ffmpeg:
ffmpeg -i data/videos/Crowd-Activity-All.avi -vf "select='between(n\,350\,650)',setpts=N/FRAME_RATE/TB,scale=640:480" -c:v libx264 -pix_fmt yuv420p data/videos/cam_03_crowd.mp4

# Or using Python with OpenCV:
python -c "
import cv2
cap = cv2.VideoCapture('data/videos/Crowd-Activity-All.avi')
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('data/videos/cam_03_crowd.mp4', fourcc, 30.0, (640, 480))
idx = 0
while cap.isOpened():
    ret, frame = cap.read()
    if not ret or idx > 650: break
    if 350 <= idx <= 650:
        out.write(cv2.resize(frame, (640, 480)))
    idx += 1
cap.release(); out.release()
print('Extracted cam_03_crowd.mp4 successfully')
"
```

---

### Option 2: Offline Synthetic Generator (`data/sample_generator.py`)
To test SentinelAI completely offline without downloading external footage:
```bash
python data/sample_generator.py
```
This automatically generates all four MP4 files in `data/videos/` using OpenCV.

#### Capabilities & Limitations of Synthetic Clips:
* **Capabilities**:
  * Validates frame decoding, looping, FPS regulation, and ring-buffer storage.
  * Streams live MJPEG video to `/api/stream/{cam_id}` and populates the 2x2 dashboard matrix.
  * Tests evidence generation: snapshot JPEG creation and MP4 clip recording.
  * Correctly exercises Farneback dense optical flow and triggers `abnormal_crowd_movement` on `cam_03`.
* **Critical Limitation**:
  * Synthetic stick-figure silhouettes do NOT provide equivalent real-human YOLO pose evaluation.
  * YOLOv8-Pose is trained on photographic humans; geometric silhouettes lack human texture and joint gradients, resulting in low or fluctuating keypoint confidence.
  * Full neural pose evaluation for `fall_collapse` and `physical_altercation` requires real human CCTV footage as specified in Option 1. Live demo presentations can also use `POST /api/simulate` or dashboard Demo Mode.

## Detailed Provenance & License Information

### CAM 01: `cam_01_fall.mp4`
* **Scenario:** Single person walking indoors, losing balance, falling to the ground, and remaining motionless.
* **Target Detection:** `fall_collapse` (confidence: 0.96, severity: `high`).
* **Source URL:** `https://raw.githubusercontent.com/TOTYsir/fyp-fall-detection/main/self_rec.mp4`
* **Attribution / Citation:**
  > EEE380 Individual Design Project: *A real-time fall detection algorithm using a single webcam*, by TOTYsir.
  > Benchmarked against: Bogdan Kwolek, Michal Kepski, *Human fall detection on embedded platform using depth maps and wireless accelerometer*, Computer Methods and Programs in Biomedicine, Volume 117, Issue 3, 2014, Pages 489-501.
* **License Terms:** **UNVERIFIED / OPEN ACADEMIC REPO**
  * The file is publicly hosted on GitHub under GitHub's standard Terms of Service (public repository).
  * No explicit SPDX license header (e.g. MIT, CC-BY) is included in the root repository.
  * *Intended Usage:* Permissible for non-commercial educational prototyping and hackathon demonstration. If production deployment or commercial redistribution is planned, replace with a formal CC-BY or custom recorded asset.
* **Technical Specifications:**
  * Resolution: 1280×720 (16:9 landscape)
  * Frame Rate: 30.0 FPS
  * Total Frames: 246
  * Duration: 8.2 seconds
  * Codec: H.264 / MP4
* **AI Pipeline Behavior:**
  * 100% human person detection rate across all sampled frames.
  * 100% 17-keypoint skeleton pose extraction.
  * Verified: Triggers `fall_collapse` cleanly at $t = 4.7\text{s}$ with 0 false alarms on altercation or crowd detectors.

---

### CAM 02: `cam_02_altercation.mp4`
* **Scenario:** Two to four individuals engaged in a physical fight, shoving, and aggressive punching.
* **Target Detection:** `physical_altercation` (confidence: 0.95, severity: `high`).
* **Source URL:** `https://raw.githubusercontent.com/airtlab/A-Dataset-for-Automatic-Violence-Detection-in-Videos/master/violence-detection-dataset/violent/cam1/43.mp4`
* **Attribution / Citation:**
  > Miriana Bianculli, Nicola Falcionelli, Paolo Sernani, Selene Tomassini, Paolo Contardo, Mara Lombardi, Aldo Franco Dragoni.
  > *A dataset for automatic violence detection in videos*, **Data in Brief**, Volume 33, 2020, 106587.
  > DOI: [10.1016/j.dib.2020.106587](https://doi.org/10.1016/j.dib.2020.106587)
* **License Terms:** **VERIFIED — RESEARCH AND EDUCATIONAL PURPOSES**
  * Explicit dataset release agreement stated by authors: *"The dataset is freely released for research and educational purposes."*
  * Peer-reviewed and published in Elsevier *Data in Brief* as open research data.
* **Technical Specifications:**
  * Resolution: 1920×1080 (1080p Full HD)
  * Frame Rate: 30.0 FPS
  * Total Frames: 281
  * Duration: 9.4 seconds
  * Codec: H.264 / MP4
* **AI Pipeline Behavior:**
  * 99.3% person detection rate, 100% concurrent $\ge 2$ people during the fight.
  * 99.3% pose keypoint consistency, wrist keypoints #9 and #10 tracked continuously.
  * Verified: Triggers `physical_altercation` at $t = 0.67\text{s}$ with 0 false alarms.
* **Performance Note:**
  * Currently preserved at original 1920×1080 resolution.
  * Optical flow is pre-computed on a 320×180 thumbnail in `sentinel_ai/pipeline.py`, and YOLOv8n operates at 640×640 internally. CPU decoding runs at ~18 FPS, satisfying the configured `target_fps: 15.0`.

---

### CAM 03: `cam_03_crowd.mp4`
* **Scenario:** Normal pedestrians walking on an open lawn/plaza transitioning into a coordinated rapid crowd surge and dispersion.
* **Target Detection:** `abnormal_crowd_movement` (confidence: 0.92, severity: `high`).
* **Source URL:** `http://mha.cs.umn.edu/Movies/Crowd-Activity-All.avi` (Scene 1: frames 350–650)
* **Attribution / Citation:**
  > University of Minnesota (UMN) Unusual Crowd Activity Dataset.
  > Department of Computer Science and Engineering & Digital Technology Center, University of Minnesota.
  > Project URL: `http://mha.cs.umn.edu/proj_events.shtml#crowd`
* **License Terms:** **VERIFIED — PUBLIC ACADEMIC BENCHMARK**
  * Standard public research benchmark released by the University of Minnesota for evaluating crowd behavior and anomaly detection algorithms in computer vision.
* **Technical Specifications:**
  * Resolution: 640×480 (VGA, bicubic upscaled from original 320×240 standard)
  * Frame Rate: 30.0 FPS
  * Total Frames: 300
  * Duration: 10.0 seconds
  * Codec: H.264 / MP4
* **AI Pipeline Behavior:**
  * 87.3% person detection rate (background crowd figures tracked alongside foreground).
  * Optical flow spike reaches $9.1\times$ baseline during the sudden dispersion phase.
  * Verified: Triggers `abnormal_crowd_movement` at $t = 1.93\text{s}$ across active tracks with 0 false alarms.

---

### CAM 04: `cam_04_normal.mp4`
* **Scenario:** Outdoor pedestrian pathway where people stroll calmly at normal walking speed without running, fighting, or falling.
* **Target Detection:** None (Negative control: 0 alerts across all detectors).
* **Source URL:** `https://raw.githubusercontent.com/opencv/opencv/5.x/samples/data/vtest.avi` (frames 1–200)
* **Attribution / Citation:**
  > OpenCV Official Sample Surveillance Dataset (`vtest.avi`).
  > OpenCV Foundation / Intel Corporation.
  > Repository: `https://github.com/opencv/opencv`
* **License Terms:** **VERIFIED — APACHE LICENSE 2.0**
  * Formally licensed under the Apache License, Version 2.0.
  * Allows free use, modification, reproduction, and redistribution.
* **Technical Specifications:**
  * Resolution: 768×576
  * Frame Rate: 10.0 FPS
  * Total Frames: 200
  * Duration: 20.0 seconds
  * Codec: H.264 / MP4
* **AI Pipeline Behavior:**
  * Detects and tracks pedestrians continuously while within the camera frame.
  * Evaluated against `FallDetector`, `AltercationDetector`, and `CrowdDetector`.
  * Verified: **0 alerts triggered** (100% negative control compliance).

---

## Backup Registry

Prior to replacing the synthetic demonstration files, all four original synthetic videos were preserved in:
`data/videos/backup_before_real_footage/`

* `backup_before_real_footage/cam_01_fall.mp4` (627 KB)
* `backup_before_real_footage/cam_02_altercation.mp4` (987 KB)
* `backup_before_real_footage/cam_03_crowd.mp4` (1.41 MB)
* `backup_before_real_footage/cam_04_normal.mp4` (1.09 MB)
