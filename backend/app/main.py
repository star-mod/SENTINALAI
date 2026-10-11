import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine, media_root
from app import models
from app.routes.api import router
from app.seed import seed_database
from app.services.ws_manager import ws_manager

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def _ensure_demo_media() -> None:
    root = media_root()
    (root / "snapshots").mkdir(parents=True, exist_ok=True)
    (root / "clips").mkdir(parents=True, exist_ok=True)
    try:
        import cv2
        import numpy as np
        from app.services.stream_service import placeholder_jpeg
        for camera_id in ("cam_01", "cam_02", "cam_03", "cam_04"):
            for incident_type in ("fall_collapse", "physical_altercation", "abnormal_crowd_movement"):
                image_path = root / "snapshots" / f"{camera_id}_{incident_type}.jpg"
                if not image_path.exists():
                    image_path.write_bytes(placeholder_jpeg("DEMO EVIDENCE"))
        for camera_id in ("cam_01", "cam_02", "cam_03", "cam_04"):
            for incident_type in ("fall_collapse", "physical_altercation", "abnormal_crowd_movement"):
                clip_path = root / "clips" / f"{camera_id}_{incident_type}.mp4"
                if clip_path.exists():
                    continue
                writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"), 12, (640, 360))
                if writer.isOpened():
                    for _ in range(24):
                        frame = np.full((360, 640, 3), (18, 28, 44), dtype=np.uint8)
                        cv2.putText(frame, "SENTINELAI  |  DEMO EVIDENCE", (30, 185), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 215, 224), 2, cv2.LINE_AA)
                        writer.write(frame)
                    writer.release()
    except Exception:
        logger.warning("Could not create placeholder evidence images", exc_info=True)


def _start_pipeline_if_enabled():
    if os.getenv("ENABLE_PIPELINE", "false").lower() != "true":
        return None
    try:
        import sys
        from pathlib import Path
        import yaml
        part2_root = Path(__file__).resolve().parents[2] / "part2"
        if part2_root.exists() and str(part2_root) not in sys.path:
            sys.path.insert(0, str(part2_root))
        from sentinel_ai.pipeline import PipelineManager
        pipeline_dir = part2_root / "sentinel_ai"
        root = media_root()
        runtime_dir = root / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with (pipeline_dir / "cameras.yaml").open(encoding="utf-8") as source:
            camera_config = yaml.safe_load(source)
        for camera in camera_config.get("cameras", []):
            filename = Path(camera.get("video_path", "")).name
            root_video = part2_root.parent / "data" / "videos" / filename
            part2_video = part2_root / "data" / "videos" / filename
            camera["video_path"] = str(root_video if root_video.is_file() else part2_video)
        with (pipeline_dir / "config.yaml").open(encoding="utf-8") as source:
            pipeline_config = yaml.safe_load(source)
        evidence = pipeline_config.setdefault("evidence", {})
        evidence["snapshots_dir"] = str(root / "snapshots")
        evidence["clips_dir"] = str(root / "clips")
        runtime_cameras = runtime_dir / "cameras.yaml"
        runtime_config = runtime_dir / "config.yaml"
        runtime_cameras.write_text(yaml.safe_dump(camera_config, sort_keys=False), encoding="utf-8")
        runtime_config.write_text(yaml.safe_dump(pipeline_config, sort_keys=False), encoding="utf-8")
        manager = PipelineManager.get_instance()
        manager.cameras_file = str(runtime_cameras)
        manager.config_file = str(runtime_config)
        manager.start()
        return manager
    except Exception:
        logger.warning("AI pipeline unavailable; API will continue in demo mode", exc_info=True)
        return None


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_demo_media()
    with SessionLocal() as db:
        seed_database(db)
    pipeline = _start_pipeline_if_enabled()
    yield
    if pipeline is not None:
        try:
            pipeline.stop()
        except Exception:
            logger.exception("Error stopping AI pipeline")


app = FastAPI(title="SentinelAI Control API", version="1.0.0", description="Evidence-backed safety incident API for authorized feeds.", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/media", StaticFiles(directory=str(media_root()), check_dir=False), name="media")


@app.websocket("/ws/incidents")
async def incidents_socket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=20)
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping", "data": {}})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)
