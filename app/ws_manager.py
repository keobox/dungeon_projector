import asyncio

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class ConnectionManager:
    """Only projectors join the broadcast group. Display state is ephemeral."""

    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)

    async def _broadcast(self, message: dict):
        for websocket in tuple(self.connections):
            try:
                await asyncio.wait_for(websocket.send_json(message), timeout=3)
            except (OSError, RuntimeError, TimeoutError, WebSocketDisconnect):
                self.disconnect(websocket)

    async def broadcast_image(self, url: str):
        await self._broadcast({"action": "show", "url": url})

    async def broadcast_command(self, cmd: str):
        if cmd != "blackout":
            raise ValueError("Unsupported command")
        await self._broadcast({"action": cmd})
