"""SQLite Database persistence for SentinelAI incidents and cameras.
Ensures zero data loss across backend restarts with WAL mode enabled.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from backend.app.schemas import Incident, Camera, Location, Verification

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sentinel.db")


class Database:
    _lock = threading.Lock()

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cameras (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stream_url TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    camera_id TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    snapshot_url TEXT NOT NULL,
                    clip_url TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    verification TEXT NOT NULL
                );
            """)
            conn.commit()

        self._seed_default_cameras()
        self._seed_initial_incidents_if_empty()

    def _seed_default_cameras(self):
        default_cams = [
            {
                "id": "cam_01",
                "name": "Central Plaza - North",
                "location": {"lat": 12.9716, "lng": 77.5946, "label": "Central Plaza"},
                "status": "online",
                "stream_url": "/api/stream/cam_01",
            },
            {
                "id": "cam_02",
                "name": "Metro Transit Hub - East Concourse",
                "location": {"lat": 12.9780, "lng": 77.6005, "label": "Transit Hub"},
                "status": "online",
                "stream_url": "/api/stream/cam_02",
            },
            {
                "id": "cam_03",
                "name": "Stadium Gate 4 - Entry Plaza",
                "location": {"lat": 12.9698, "lng": 77.5890, "label": "Stadium Gate 4"},
                "status": "online",
                "stream_url": "/api/stream/cam_03",
            },
            {
                "id": "cam_04",
                "name": "Financial District - Main Arcade",
                "location": {"lat": 12.9752, "lng": 77.5912, "label": "Financial District"},
                "status": "online",
                "stream_url": "/api/stream/cam_04",
            },
        ]

        with self._lock, self._get_connection() as conn:
            for cam in default_cams:
                conn.execute("""
                    INSERT OR REPLACE INTO cameras (id, name, location, status, stream_url)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    cam["id"],
                    cam["name"],
                    json.dumps(cam["location"]),
                    cam["status"],
                    cam["stream_url"],
                ))
            conn.commit()

    def _seed_initial_incidents_if_empty(self):
        with self._lock, self._get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            if count == 0:
                now = datetime.now(timezone.utc)
                seed_data = [
                    {
                        "id": "inc_0001",
                        "camera_id": "cam_01",
                        "camera_name": "Central Plaza - North",
                        "location": {"lat": 12.9716, "lng": 77.5946, "label": "Central Plaza"},
                        "type": "fall_collapse",
                        "confidence": 0.92,
                        "severity": "high",
                        "timestamp": (now - timedelta(minutes=14)).isoformat(),
                        "status": "new",
                        "snapshot_url": "/media/snapshots/cam_01_fall.jpg",
                        "clip_url": "/media/clips/cam_01_fall.mp4",
                        "notes": "Elderly pedestrian sudden collapse near north fountain bench.",
                        "verification": {"window_seconds": 2.5, "frames_confirmed": 34, "frames_required": 25},
                    },
                    {
                        "id": "inc_0002",
                        "camera_id": "cam_02",
                        "camera_name": "Metro Transit Hub - East Concourse",
                        "location": {"lat": 12.9780, "lng": 77.6005, "label": "Transit Hub"},
                        "type": "physical_altercation",
                        "confidence": 0.88,
                        "severity": "high",
                        "timestamp": (now - timedelta(minutes=42)).isoformat(),
                        "status": "acknowledged",
                        "snapshot_url": "/media/snapshots/cam_02_altercation.jpg",
                        "clip_url": "/media/clips/cam_02_altercation.mp4",
                        "notes": "Escalation between two individuals near ticket barrier B.",
                        "verification": {"window_seconds": 2.5, "frames_confirmed": 38, "frames_required": 30},
                    },
                    {
                        "id": "inc_0003",
                        "camera_id": "cam_03",
                        "camera_name": "Stadium Gate 4 - Entry Plaza",
                        "location": {"lat": 12.9698, "lng": 77.5890, "label": "Stadium Gate 4"},
                        "type": "abnormal_crowd_movement",
                        "confidence": 0.78,
                        "severity": "medium",
                        "timestamp": (now - timedelta(hours=2, minutes=10)).isoformat(),
                        "status": "resolved",
                        "snapshot_url": "/media/snapshots/cam_03_crowd.jpg",
                        "clip_url": "/media/clips/cam_03_crowd.mp4",
                        "notes": "Localized surge at turnstiles resolved by security personnel.",
                        "verification": {"window_seconds": 2.5, "frames_confirmed": 28, "frames_required": 25},
                    },
                ]

                for item in seed_data:
                    conn.execute("""
                        INSERT INTO incidents (
                            id, camera_id, camera_name, location, type, confidence,
                            severity, timestamp, status, snapshot_url, clip_url, notes, verification
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item["id"],
                        item["camera_id"],
                        item["camera_name"],
                        json.dumps(item["location"]),
                        item["type"],
                        item["confidence"],
                        item["severity"],
                        item["timestamp"],
                        item["status"],
                        item["snapshot_url"],
                        item["clip_url"],
                        item["notes"],
                        json.dumps(item["verification"]),
                    ))
                conn.commit()

    def get_cameras(self) -> List[Camera]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM cameras ORDER BY id ASC").fetchall()
            return [
                Camera(
                    id=r["id"],
                    name=r["name"],
                    location=Location(**json.loads(r["location"])),
                    status=r["status"],
                    stream_url=r["stream_url"],
                )
                for r in rows
            ]

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        with self._get_connection() as conn:
            r = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
            if not r:
                return None
            return Camera(
                id=r["id"],
                name=r["name"],
                location=Location(**json.loads(r["location"])),
                status=r["status"],
                stream_url=r["stream_url"],
            )

    def get_incidents(
        self,
        status: Optional[str] = None,
        type_: Optional[str] = None,
        camera_id: Optional[str] = None
    ) -> List[Incident]:
        query = "SELECT * FROM incidents WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if type_:
            query += " AND type = ?"
            params.append(type_)
        if camera_id:
            query += " AND camera_id = ?"
            params.append(camera_id)

        query += " ORDER BY timestamp DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                Incident(
                    id=r["id"],
                    camera_id=r["camera_id"],
                    camera_name=r["camera_name"],
                    location=Location(**json.loads(r["location"])),
                    type=r["type"],
                    confidence=r["confidence"],
                    severity=r["severity"],
                    timestamp=r["timestamp"],
                    status=r["status"],
                    snapshot_url=r["snapshot_url"],
                    clip_url=r["clip_url"],
                    notes=r["notes"] or "",
                    verification=Verification(**json.loads(r["verification"])),
                )
                for r in rows
            ]

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._get_connection() as conn:
            r = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if not r:
                return None
            return Incident(
                id=r["id"],
                camera_id=r["camera_id"],
                camera_name=r["camera_name"],
                location=Location(**json.loads(r["location"])),
                type=r["type"],
                confidence=r["confidence"],
                severity=r["severity"],
                timestamp=r["timestamp"],
                status=r["status"],
                snapshot_url=r["snapshot_url"],
                clip_url=r["clip_url"],
                notes=r["notes"] or "",
                verification=Verification(**json.loads(r["verification"])),
            )

    def create_incident(self, inc_data: Dict[str, Any]) -> Incident:
        with self._lock, self._get_connection() as conn:
            # Generate next ID if not provided
            if "id" not in inc_data or not inc_data["id"]:
                count = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
                inc_data["id"] = f"inc_{count + 1:04d}"

            if "status" not in inc_data:
                inc_data["status"] = "new"

            location_dict = inc_data["location"] if isinstance(inc_data["location"], dict) else inc_data["location"].model_dump()
            verif_dict = inc_data["verification"] if isinstance(inc_data["verification"], dict) else inc_data["verification"].model_dump()

            conn.execute("""
                INSERT OR REPLACE INTO incidents (
                    id, camera_id, camera_name, location, type, confidence,
                    severity, timestamp, status, snapshot_url, clip_url, notes, verification
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inc_data["id"],
                inc_data["camera_id"],
                inc_data["camera_name"],
                json.dumps(location_dict),
                inc_data["type"],
                float(inc_data["confidence"]),
                inc_data["severity"],
                inc_data["timestamp"],
                inc_data["status"],
                inc_data["snapshot_url"],
                inc_data["clip_url"],
                inc_data.get("notes", ""),
                json.dumps(verif_dict),
            ))
            conn.commit()

        return self.get_incident(inc_data["id"])

    def update_incident(self, incident_id: str, status: Optional[str] = None, notes: Optional[str] = None) -> Optional[Incident]:
        with self._lock, self._get_connection() as conn:
            existing = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if not existing:
                return None

            updates = []
            params = []
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)

            if updates:
                params.append(incident_id)
                conn.execute(f"UPDATE incidents SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()

        return self.get_incident(incident_id)

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM incidents ORDER BY timestamp ASC").fetchall()

            total = len(rows)
            by_type = {"physical_altercation": 0, "fall_collapse": 0, "abnormal_crowd_movement": 0, "vehicle_accident": 0}
            by_status = {"new": 0, "acknowledged": 0, "resolved": 0}
            cam_counts: Dict[str, Dict[str, Any]] = {}
            hour_counts: Dict[str, int] = {}

            # Initialize 24-hour slots
            for h in range(8, 22):
                hour_counts[f"{h:02d}:00"] = 0

            for r in rows:
                t = r["type"]
                s = r["status"]
                cid = r["camera_id"]
                cname = r["camera_name"]

                if t in by_type:
                    by_type[t] += 1
                if s in by_status:
                    by_status[s] += 1

                if cid not in cam_counts:
                    cam_counts[cid] = {"camera_id": cid, "name": cname, "count": 0}
                cam_counts[cid]["count"] += 1

                # Parse timestamp hour
                try:
                    ts_dt = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
                    hr_str = f"{ts_dt.hour:02d}:00"
                    hour_counts[hr_str] = hour_counts.get(hr_str, 0) + 1
                except Exception:
                    pass

            by_hour = [{"hour": h, "count": c} for h, c in sorted(hour_counts.items())]
            by_camera = list(cam_counts.values())

            return {
                "total": total,
                "by_type": by_type,
                "by_status": by_status,
                "by_hour": by_hour,
                "by_camera": by_camera,
            }


db = Database()
