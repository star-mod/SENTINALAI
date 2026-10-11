from pathlib import Path


CAMERA_FILES = {
    "cam_01": "cam_01_fall.mp4",
    "cam_02": "cam_02_altercation.mp4",
    "cam_03": "cam_03_crowd.mp4",
    "cam_04": "cam_04_normal.mp4",
}
TYPE_CAMERAS = {
    "fall_collapse": "cam_01",
    "physical_altercation": "cam_02",
    "abnormal_crowd_movement": "cam_03",
}


def video_source(camera_id: str) -> Path | None:
    filename = CAMERA_FILES.get(camera_id)
    if filename is None:
        return None
    root = Path(__file__).resolve().parents[3]
    root_video = root / "data" / "videos" / filename
    part2_video = root / "part2" / "data" / "videos" / filename
    if root_video.is_file():
        return root_video
    if part2_video.is_file():
        return part2_video
    return None


def incident_video_url(incident_type: str) -> str:
    return f"/api/incident-video/{incident_type}"


def resolve_incident_clip(camera_id: str, incident_type: str, clip_url: str) -> str:
    if clip_url == f"/media/clips/{camera_id}_{incident_type}.mp4":
        return incident_video_url(incident_type)
    return clip_url