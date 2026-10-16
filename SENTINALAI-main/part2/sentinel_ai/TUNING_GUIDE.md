# SentinelAI Detector Tuning Guide

This guide details parameter calibration in `sentinel_ai/config.yaml` to optimize detection sensitivity and eliminate false positives across diverse camera angles and environments.

---

## 1. Fall & Collapse Detector (`fall_collapse`)

| Parameter | Default | Purpose & Calibration Advice |
|---|---|---|
| `drop_velocity_threshold` | `0.08` | Minimum normalized vertical drop velocity per frame. If falls fail to register on cameras mounted high up (overhead view), decrease to `0.05`. If rapid sitting triggers false alarms, increase to `0.12`. |
| `aspect_ratio_threshold` | `1.15` | Bounding box width / height ratio ($w/h$). When a person is prone/supine, $w/h > 1.0$. If people lying on low benches trigger false positives, increase to `1.30`. If partial camera occlusion cuts off legs, lower to `0.95`. |
| `stillness_threshold` | `0.04` | Maximum normalized displacement of center-of-mass between frames. Ensures the person remains down. If post-fall twitching prevents detection, increase to `0.06`. |
| `frames_required` | `15` | Temporal confirmation requirement (~1.0s at 15 FPS). Decrease to `10` for faster alerts; increase to `20` to reject brief stumble recoveries. |

---

## 2. Physical Altercation Detector (`physical_altercation`)

| Parameter | Default | Purpose & Calibration Advice |
|---|---|---|
| `proximity_threshold` | `0.22` | Maximum normalized Euclidean distance between track centers. If crowds standing close in queues trigger false alerts, decrease to `0.15`. For wide-angle lenses where people appear small, increase to `0.28`. |
| `wrist_velocity_threshold` | `0.06` | Normalized wrist and elbow swinging speed. Distinguishes violent strikes/punches from normal hand gestures. If expressive speaking triggers alarms, increase to `0.08`. If grapples with slow pushing fail to trigger, lower to `0.04`. |
| `rapid_approach_threshold` | `0.08` | Rate of change in relative distance ($d(t) - d(t-1)$). Detects sudden aggressive lunges and charges. |
| `frames_required` | `18` | Sustained aggression requirement (~1.2s at 15 FPS). Ensures brief handshakes or passing pedestrians on sidewalks never trigger an alert. |

---

## 3. Abnormal Crowd Movement Detector (`abnormal_crowd_movement`)

| Parameter | Default | Purpose & Calibration Advice |
|---|---|---|
| `optical_flow_spike_factor` | `2.2` | Multiplier above the median rolling baseline of optical flow velocity. If normal rush hour pedestrian traffic triggers alerts, raise to `2.8`. For gradual panic dispersals, lower to `1.8`. |
| `direction_divergence_threshold` | `0.40` | Directional entropy/variance across tracks ($0$ = unidirectional flow, $1$ = completely chaotic scattering). High values identify crowd stampedes and panic dispersals. |
| `min_people_for_crowd` | `3` | Minimum track count required before evaluating crowd dynamics. Ignores individual runners or vehicles. |
| `frames_required` | `20` | Requires ~1.3s of sustained abnormal flow. Filters out momentary camera vibrations or wind-blown tree branches. |

---

## 4. Global Pipeline & Cooldown

| Parameter | Default | Purpose |
|---|---|---|
| `target_fps` | `15` | Target processing frame rate. Recommended 15 FPS for real-time CPU performance on laptops. |
| `cooldown_seconds` | `20.0` | Prevents duplicate alert spam for the same ongoing incident on a camera feed. |
| `clip_pre_seconds` | `3.0` | Seconds of video saved prior to the incident verification moment. |
| `clip_post_seconds` | `3.0` | Seconds of video saved following the incident verification moment. |
