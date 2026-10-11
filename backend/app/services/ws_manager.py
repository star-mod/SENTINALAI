import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.connections.discard(websocket)

    async def broadcast(self, event: str, data: dict) -> None:
        async with self._lock:
            connections = tuple(self.connections)
        stale = []
        for websocket in connections:
            try:
                await websocket.send_json({"event": event, "data": data})
            except Exception:
                logger.debug("Removing disconnected WebSocket client", exc_info=True)
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(websocket)


ws_manager = WebSocketManager()