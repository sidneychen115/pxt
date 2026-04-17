import json
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def broadcast(self, channel: str, data: dict) -> None:
        message = json.dumps({"channel": channel, "data": data})
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except (RuntimeError, OSError):
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


ws_manager = WebSocketManager()
