"""
Мост между процессом Celery-воркера и процессом FastAPI для доставки
уведомлений о дедлайнах через WebSocket.

Celery-воркер (отдельный процесс) не имеет доступа к in-memory
ConnectionManager внутри процесса FastAPI, поэтому события публикуются
в Redis Pub/Sub, а FastAPI подписывается на канал в фоновой задаче
(см. app/main.py) и рассылает их подключённым пользователям.
"""

import json
import logging

import redis as redis_sync
import redis.asyncio as redis_async

from app.config import settings
from app.services.websocket_manager import user_manager

logger = logging.getLogger(__name__)

NOTIFICATIONS_CHANNEL = "ws:notifications"

_sync_redis_client: redis_sync.Redis | None = None


def _get_sync_redis_client() -> redis_sync.Redis:
    """Синхронный клиент для публикации из Celery-задач (Celery не async)."""
    global _sync_redis_client
    if _sync_redis_client is None:
        _sync_redis_client = redis_sync.Redis.from_url(settings.REDIS_URL)
    return _sync_redis_client


def publish_notification_sync(payload: dict) -> None:
    """Публикует уведомление в Redis. Вызывается из Celery-задачи."""
    _get_sync_redis_client().publish(NOTIFICATIONS_CHANNEL, json.dumps(payload))


async def listen_for_notifications() -> None:
    """Слушает Redis Pub/Sub и рассылает уведомления по WebSocket-подключениям
    этого инстанса FastAPI. Запускается как фоновая задача в lifespan."""
    client = redis_async.Redis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(NOTIFICATIONS_CHANNEL)
    logger.info("Подписались на канал Redis '%s'", NOTIFICATIONS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                payload = json.loads(message["data"])
            except (TypeError, ValueError):
                logger.warning("Некорректное сообщение в '%s': %s", NOTIFICATIONS_CHANNEL, message)
                continue

            recipient_id = payload.get("recipient_id")
            if recipient_id is None:
                continue
            await user_manager.broadcast(recipient_id, {"type": "deadline", **payload})
    finally:
        await pubsub.unsubscribe(NOTIFICATIONS_CHANNEL)
        await client.close()