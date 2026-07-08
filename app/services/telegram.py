import hashlib
import hmac
import html
import logging
import time

import httpx

from app.config import settings
from app.exceptions import (
    TelegramConfigurationException,
    TelegramServiceException,
)
from app.models import Todo as TodoORM

logger = logging.getLogger(__name__)

# Кэш username бота (getMe), чтобы не дёргать API на каждый запрос ссылки
_bot_username_cache: str | None = None


class TelegramService:
    """Отправка заметок в Telegram и привязка чата к аккаунту.

    Код привязки передаётся в deep-link t.me/<bot>?start=<code>.
    Telegram ограничивает start-параметр 64 символами [A-Za-z0-9_-],
    поэтому вместо JWT используется компактный HMAC-код вида
    "<user_id>_<expires_ts>_<подпись>".
    """

    def __init__(self) -> None:
        self._token = settings.TELEGRAM_BOT_TOKEN
        self._base_url = settings.TELEGRAM_API_BASE_URL.rstrip("/")
        self._timeout = settings.TELEGRAM_TIMEOUT_SECONDS

    def _ensure_configured(self) -> None:
        if not self._token:
            raise TelegramConfigurationException(
                "Telegram не настроен: задайте TELEGRAM_BOT_TOKEN в .env."
            )

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    async def _call_api(self, method: str, payload: dict | None = None) -> dict:
        self._ensure_configured()
        url = f"{self._base_url}/bot{self._token}/{method}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload or {})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Telegram API %s returned %s: %s",
                method,
                exc.response.status_code,
                exc.response.text,
            )
            raise TelegramServiceException(
                "Telegram вернул ошибку при обработке запроса."
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Telegram request %s failed: %s", method, exc)
            raise TelegramServiceException(
                "Не удалось обратиться к Telegram Bot API."
            ) from exc

        data = response.json()
        if not data.get("ok"):
            logger.error("Telegram API %s returned not ok: %s", method, data)
            raise TelegramServiceException(
                "Telegram вернул ошибку при обработке запроса."
            )
        return data.get("result") or {}

    async def get_bot_username(self) -> str:
        """Username бота: из настроек или через getMe (с кэшем)."""
        global _bot_username_cache
        if settings.TELEGRAM_BOT_USERNAME:
            return settings.TELEGRAM_BOT_USERNAME.lstrip("@")
        if _bot_username_cache:
            return _bot_username_cache
        me = await self._call_api("getMe")
        username = me.get("username")
        if not username:
            raise TelegramServiceException("Telegram не вернул username бота.")
        _bot_username_cache = username
        return username

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> None:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._call_api("sendMessage", payload)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None
    ) -> None:
        """Подтверждает нажатие inline-кнопки (убирает «часики» в клиенте)."""
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        await self._call_api("answerCallbackQuery", payload)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._call_api("editMessageText", payload)

    async def set_my_commands(self, commands: list[dict]) -> None:
        await self._call_api("setMyCommands", {"commands": commands})

    async def send_todo(self, chat_id: int, todo: TodoORM) -> None:
        """Отправляет заметку в чат пользователя."""
        await self.send_message(chat_id, format_todo_message(todo))

    # --- Привязка чата (deep-link коды) ---

    def create_link_code(self, user_id: int) -> str:
        """Генерирует подписанный код привязки для deep-link."""
        expires_at = int(time.time()) + settings.TELEGRAM_LINK_TTL_MINUTES * 60
        signature = _sign_link_payload(user_id, expires_at)
        return f"{user_id}_{expires_at}_{signature}"

    def verify_link_code(self, code: str) -> int | None:
        """Проверяет код привязки, возвращает user_id или None."""
        parts = code.split("_")
        if len(parts) != 3:
            return None
        raw_user_id, raw_expires, signature = parts
        if not raw_user_id.isdigit() or not raw_expires.isdigit():
            return None
        user_id, expires_at = int(raw_user_id), int(raw_expires)
        expected = _sign_link_payload(user_id, expires_at)
        if not hmac.compare_digest(signature, expected):
            return None
        if time.time() > expires_at:
            return None
        return user_id

    async def build_link_url(self, user_id: int) -> str:
        """Deep-link для привязки: t.me/<bot>?start=<code>."""
        self._ensure_configured()
        username = await self.get_bot_username()
        return f"https://t.me/{username}?start={self.create_link_code(user_id)}"


def _sign_link_payload(user_id: int, expires_at: int) -> str:
    message = f"telegram-link:{user_id}:{expires_at}"
    digest = hmac.new(
        settings.JWT_SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def format_todo_message(todo: TodoORM) -> str:
    """Формирует HTML-сообщение с заметкой для Telegram."""
    lines = [f"📝 <b>{html.escape(todo.title or 'Без заголовка')}</b>"]
    if todo.details:
        lines.append("")
        lines.append(html.escape(todo.details))
    if todo.spacy_summary:
        lines.append("")
        lines.append(f"📄 <b>Реферат (spaCy):</b> {html.escape(todo.spacy_summary)}")
    if todo.llm_summary:
        lines.append("")
        lines.append(f"🤖 <b>Реферат (LLM):</b> {html.escape(todo.llm_summary)}")
    lines.append("")
    if todo.tag:
        lines.append(f"🏷 Тег: {html.escape(todo.tag)}")
    if todo.due_at:
        lines.append(f"📅 Срок: {todo.due_at.strftime('%d.%m.%Y %H:%M')}")
    lines.append("✅ Выполнена" if todo.completed else "⏳ Не выполнена")
    return "\n".join(lines)


MAX_TODO_CARDS = 10
CARD_DETAILS_MAX_CHARS = 200


def build_users_keyboard(users) -> dict:
    """Inline-клавиатура выбора пользователя (callback_data: tasks:<user_id>)."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"{user.first_name} {user.last_name} ({user.email})",
                    "callback_data": f"tasks:{user.id}",
                }
            ]
            for user in users
        ]
    }


def build_complete_keyboard(todo_id: int) -> dict:
    """Кнопка подтверждения выполнения под карточкой задачи."""
    return {
        "inline_keyboard": [
            [{"text": "✅ Отметить выполненной", "callback_data": f"done:{todo_id}"}]
        ]
    }


def build_completed_keyboard() -> dict:
    """Кнопка-индикатор под карточкой уже выполненной задачи (не активна)."""
    return {
        "inline_keyboard": [
            [{"text": "🎉 Задача выполнена", "callback_data": "noop"}]
        ]
    }


def format_pending_todos_header(user, total: int) -> str:
    author = html.escape(f"{user.first_name} {user.last_name}")
    if total == 0:
        return f"📋 У пользователя <b>{author}</b> нет невыполненных задач 🎉"
    return f"📋 Невыполненные задачи <b>{author}</b> — всего {total}:"


def format_todo_card(todo) -> str:
    """Карточка задачи для Telegram: заголовок, суть, тег, срок, статус."""
    lines = [f"📌 <b>{html.escape(todo.title or 'Без заголовка')}</b>"]

    # Краткое описание: реферат, если есть, иначе укороченный текст задачи
    summary = todo.llm_summary or todo.spacy_summary
    body = summary or todo.details
    if body:
        body = body.strip()
        if len(body) > CARD_DETAILS_MAX_CHARS:
            body = body[:CARD_DETAILS_MAX_CHARS].rstrip() + "…"
        lines.append(html.escape(body))

    meta = []
    if todo.tag:
        meta.append(f"🏷 {html.escape(todo.tag)}")
    if todo.due_at:
        meta.append(f"📅 до {todo.due_at.strftime('%d.%m.%Y %H:%M')}")
    if meta:
        lines.append("")
        lines.append("  |  ".join(meta))

    lines.append("")
    if todo.completed:
        completed_at = (
            f" ({todo.completed_at.strftime('%d.%m.%Y %H:%M')})"
            if todo.completed_at
            else ""
        )
        lines.append(f"✅ <b>Выполнена</b>{completed_at}")
    else:
        lines.append("⏳ Не выполнена")
    return "\n".join(lines)
