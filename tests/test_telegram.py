"""Юнит-тесты Telegram-интеграции: коды привязки и формат сообщения.

Не требуют сети, БД и Elasticsearch.
"""

import time
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.telegram import (
    CARD_DETAILS_MAX_CHARS,
    TelegramService,
    _sign_link_payload,
    build_complete_keyboard,
    build_completed_keyboard,
    build_users_keyboard,
    format_pending_todos_header,
    format_todo_card,
    format_todo_message,
)


@pytest.fixture
def service() -> TelegramService:
    return TelegramService()


def _make_todo(**overrides):
    fields = {
        "title": "Купить продукты",
        "details": "Молоко, хлеб <и> яйца",
        "tag": "быт",
        "due_at": datetime(2026, 7, 10, 18, 30),
        "completed": False,
        "completed_at": None,
        "spacy_summary": "Список покупок на вечер",
        "llm_summary": "Заметка о покупке <базовых> продуктов",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestLinkCode:
    def test_roundtrip(self, service):
        code = service.create_link_code(42)
        assert service.verify_link_code(code) == 42

    def test_fits_telegram_start_param(self, service):
        # Telegram ограничивает start-параметр 64 символами [A-Za-z0-9_-]
        code = service.create_link_code(2**31)
        assert len(code) <= 64
        assert all(c.isalnum() or c in "_-" for c in code)

    def test_tampered_user_id_rejected(self, service):
        code = service.create_link_code(42)
        _, expires, signature = code.split("_")
        assert service.verify_link_code(f"1_{expires}_{signature}") is None

    def test_expired_code_rejected(self, service):
        expires_at = int(time.time()) - 1
        code = f"42_{expires_at}_{_sign_link_payload(42, expires_at)}"
        assert service.verify_link_code(code) is None

    @pytest.mark.parametrize(
        "bad_code",
        ["", "abc", "42_abc_def", "42_123", "a_b_c_d", "//42_1_x"],
    )
    def test_malformed_code_rejected(self, service, bad_code):
        assert service.verify_link_code(bad_code) is None


class TestFormatTodoMessage:
    def test_contains_fields_and_escapes_html(self):
        message = format_todo_message(_make_todo())
        assert "<b>Купить продукты</b>" in message
        assert "Молоко, хлеб &lt;и&gt; яйца" in message
        assert "Тег: быт" in message
        assert "Срок: 10.07.2026 18:30" in message
        assert "⏳ Не выполнена" in message
        assert "Реферат (spaCy):</b> Список покупок на вечер" in message
        assert "Реферат (LLM):</b> Заметка о покупке &lt;базовых&gt; продуктов" in message

    def test_completed_and_empty_fields(self):
        todo = _make_todo(
            details=None,
            tag=None,
            due_at=None,
            completed=True,
            spacy_summary=None,
            llm_summary=None,
        )
        message = format_todo_message(todo)
        assert "✅ Выполнена" in message
        assert "Тег:" not in message
        assert "Срок:" not in message
        assert "Реферат" not in message


def _make_user(user_id=1, first_name="Иван", last_name="Петров", email="ivan@mail.ru"):
    return SimpleNamespace(
        id=user_id, first_name=first_name, last_name=last_name, email=email
    )


class TestKeyboards:
    def test_users_keyboard_builds_button_per_user(self):
        users = [_make_user(1), _make_user(2, "Анна", "Иванова", "anna@mail.ru")]
        keyboard = build_users_keyboard(users)
        rows = keyboard["inline_keyboard"]
        assert len(rows) == 2
        assert rows[0][0]["callback_data"] == "tasks:1"
        assert rows[1][0]["text"] == "Анна Иванова (anna@mail.ru)"
        assert rows[1][0]["callback_data"] == "tasks:2"

    def test_complete_keyboard(self):
        keyboard = build_complete_keyboard(7)
        button = keyboard["inline_keyboard"][0][0]
        assert button["callback_data"] == "done:7"
        assert "Отметить выполненной" in button["text"]

    def test_completed_keyboard_is_indicator(self):
        keyboard = build_completed_keyboard()
        button = keyboard["inline_keyboard"][0][0]
        assert button["callback_data"] == "noop"
        assert "выполнена" in button["text"].lower()


class TestPendingTodosHeader:
    def test_with_todos(self):
        header = format_pending_todos_header(_make_user(), 5)
        assert "Невыполненные задачи <b>Иван Петров</b> — всего 5:" in header

    def test_no_todos(self):
        header = format_pending_todos_header(_make_user(), 0)
        assert "нет невыполненных задач" in header


class TestFormatTodoCard:
    def test_prefers_summary_over_details(self):
        card = format_todo_card(_make_todo())
        assert "📌 <b>Купить продукты</b>" in card
        assert "Заметка о покупке &lt;базовых&gt; продуктов" in card
        assert "Молоко" not in card
        assert "🏷 быт" in card
        assert "📅 до 10.07.2026 18:30" in card
        assert "⏳ Не выполнена" in card

    def test_falls_back_to_truncated_details(self):
        todo = _make_todo(
            spacy_summary=None, llm_summary=None, details="х" * 500
        )
        card = format_todo_card(todo)
        assert "х" * CARD_DETAILS_MAX_CHARS + "…" in card
        assert "х" * (CARD_DETAILS_MAX_CHARS + 1) not in card

    def test_completed_card_shows_date_and_status(self):
        todo = _make_todo(
            completed=True, completed_at=datetime(2026, 7, 4, 12, 0)
        )
        card = format_todo_card(todo)
        assert "✅ <b>Выполнена</b> (04.07.2026 12:00)" in card
        assert "⏳" not in card
