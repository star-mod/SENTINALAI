import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Camera, Incident
from app.services.video_service import incident_video_url


CAMERAS = [
    ("cam_01", "Central Plaza - North", 12.9716, 77.5946, "Central Plaza"),
    ("cam_02", "Metro Transit Hub - East Concourse", 12.9780, 77.6005, "Transit Hub"),
    ("cam_03", "Stadium Gate 4 - Entry Plaza", 12.9698, 77.5890, "Stadium Gate 4"),
    ("cam_04", "Financial District - Main Arcade", 12.9752, 77.5912, "Financial District"),
]
TYPES = ("physical_altercation", "fall_collapse", "abnormal_crowd_movement", "vehicle_accident")
SEED_COUNT = 6
SEED_NOTES = {"Historical demo record", "Verified event for operator review"}


def seed_database(db: Session) -> None:
    for camera_id, name, lat, lng, label in CAMERAS:
        if db.get(Camera, camera_id) is None:
            db.add(Camera(
                id=camera_id, name=name,
                location=json.dumps({"lat": lat, "lng": lng, "label": label}),
                status="online", stream_url=f"/api/stream/{camera_id}",
            ))
    db.flush()

    existing_incidents = db.scalars(select(Incident)).all()
    seed_records = [row for row in existing_incidents if row.notes in SEED_NOTES and row.id.startswith("inc_")]
    for row in seed_records:
        suffix = row.id[4:]
        if suffix.isdigit() and int(suffix) > SEED_COUNT:
            db.delete(row)
    if existing_incidents:
        db.commit()
        return

    rng = random.Random(2026)
    now = datetime.now(timezone.utc)
    for index in range(SEED_COUNT):
        camera_id, camera_name, lat, lng, label = CAMERAS[index % len(CAMERAS)]
        incident_type = TYPES[index % len(TYPES)]
        confidence = round(rng.uniform(0.63, 0.97), 2)
        severity = "high" if confidence >= 0.85 else "medium" if confidence >= 0.70 else "low"
        minutes_ago = (index * 53 + 11) % (24 * 60)
        if index < 3:
            minutes_ago += 90
        db.add(Incident(
            id=f"inc_{index + 1:04d}", camera_id=camera_id, camera_name=camera_name,
            event_id=f"seed_{index + 1:04d}",
            location=json.dumps({"lat": lat, "lng": lng, "label": label}),
            type=incident_type, confidence=confidence, severity=severity,
            timestamp=now - timedelta(minutes=minutes_ago),
            status="new" if index in (0, 9) else "acknowledged" if index % 4 == 0 else "resolved",
            snapshot_url=f"/media/snapshots/{camera_id}_{incident_type}.jpg",
            clip_url=incident_video_url(incident_type),
            notes="Historical demo record" if index else "Verified event for operator review",
            verification=json.dumps({"window_seconds": 2.5, "frames_confirmed": 30 + index % 12, "frames_required": 25}),
            source="simulation", priority="normal", workflow_status="not_configured",
            updated_at=now - timedelta(minutes=minutes_ago),
            workflow_updated_at=now - timedelta(minutes=minutes_ago),
        ))
    db.commit()