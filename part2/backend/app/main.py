"""Main FastAPI Application Entrypoint for SentinelAI.
Hosts REST API, WebSocket incident stream, MJPEG camera proxies, and static media.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.router import api_router
from backend.app.websocket import ws_manager
from sentinel_ai.pipeline import PipelineManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure media directories exist
    os.makedirs("./media/snapshots", exist_ok=True)
    os.makedirs("./media/clips", exist_ok=True)

    # Start Sentinel AI pipeline in background if enabled
    enable_pipeline = os.environ.get("ENABLE_PIPELINE", "true").lower() == "true"
    pipeline_manager = PipelineManager.get_instance()

    if enable_pipeline:
        try:
            print("[SentinelAI Backend] Starting AI detection pipeline workers...")
            pipeline_manager.start()
        except Exception as e:
            print(f"[SentinelAI Backend Warning] Could not start pipeline workers: {e}")

    yield

    if enable_pipeline:
        try:
            print("[SentinelAI Backend] Stopping AI detection pipeline workers...")
            pipeline_manager.stop()
        except Exception as e:
            pass


app = FastAPI(
    title="SentinelAI — Public Safety Incident Detection API",
    description="Real-time CCTV safety monitoring, incident verification, and SOC operations control.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration strictly adhering to contract
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static media directories
os.makedirs("./media/snapshots", exist_ok=True)
os.makedirs("./media/clips", exist_ok=True)
app.mount("/media", StaticFiles(directory="./media"), name="media")

# Include REST API endpoints
app.include_router(api_router, prefix="/api")


# WebSocket live incident feed
@app.websocket("/ws/incidents")
async def websocket_incidents_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep socket open and receive heartbeat/messages from client
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
