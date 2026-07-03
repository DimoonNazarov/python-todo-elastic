import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, todo_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(todo_id, []).append(websocket)

    def disconnect(self, todo_id: int, websocket: WebSocket) -> None:
        if todo_id in self._connections:
            try:
                self._connections[todo_id].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, todo_id: int, data: dict) -> None:
        connections = list(self._connections.get(todo_id, []))
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(todo_id, ws)


manager = ConnectionManager()
