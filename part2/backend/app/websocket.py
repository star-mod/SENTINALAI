"""WebSocket Manager for SentinelAI.
Handles live incident stream broadcasting with graceful connection management.
"""

import asyncio
import json
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

from backend.app.schemas import Incident


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WebSocket] Client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WebSocket] Client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast_event(self, event_name: str, incident: Incident):
        """Broadcasts {event: 'incident.created'|'incident.updated', data: <Incident>}."""
        message = {
            "event": event_name,
            "data": incident.model_dump()
        }
        text = json.dumps(message)
        dead_connections = []

        for connection in list(self.active_connections):
            try:
                await connection.send_text(text)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


ws_manager = ConnectionManager()
