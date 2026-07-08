import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Зарезервированный канал для страницы списка задач (реальные todo_id начинаются с 1)
TODOS_FEED_CHANNEL = 0


class ConnectionManager:
    """Держит WebSocket-подключения, сгруппированные по произвольному int-ключу
    (todo_id для комментариев, user_id для уведомлений)."""

    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, key: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(key, []).append(websocket)

    def disconnect(self, key: int, websocket: WebSocket) -> None:
        if key in self._connections:
            try:
                self._connections[key].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, key: int, data: dict) -> None:
        connections = list(self._connections.get(key, []))
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(key, ws)


manager = ConnectionManager()
user_manager = ConnectionManager()
