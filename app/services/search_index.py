import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def _get_value(item: Any, field: str, default: Any = None) -> Any:
    """Извлекает значение поля из объекта или словаря, возвращает default при отсутствии."""
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def _set_value(item: Any, field: str, value: Any) -> Any:
    """Устанавливает значение поля в объекте или словаре, возвращает изменённый элемент."""
    if isinstance(item, Mapping):
        item[field] = value
    else:
        setattr(item, field, value)
    return item


def _iso_format(value: Any) -> str | None:
    """
    Преобразует datetime объект в ISO-строку.

    Используется при подготовке документов для Elasticsearch,
    который ожидает даты в строковом формате.
    """
    return value.isoformat() if value else None


@dataclass
class TodoClassificationService:
    """Сервис для определения уровня секретности и маскировки секретных фраз в задачах."""

    PRIORITY_ORDER = [
        "особой важности",
        "совершенно секретно",
        "для служебного пользования",
        "конфиденциально",
        "дсп",
        "секретно",
    ]

    REPLACEMENTS = {
        "особой важности": "не интересссно",
        "совершенно секретно": "не интерессно",
        "для служебного пользования": "не интересно",
        "конфиденциально": "не интересно",
        "дсп": "не интересно",
        "секретно": "не интересно",
    }

    def enrich(self, item: Any) -> Any:
        """Обогащает объект задачи полями display_title, display_details,
        классификацией и маскировкой."""
        title = _get_value(item, "title")
        details = _get_value(item, "details")
        masked_title = _get_value(item, "masked_title")
        masked_details = _get_value(item, "masked_details")
        classification = _get_value(item, "classification_level")

        if not classification or masked_title is None:
            fields = self.build_document_fields(title, details)  # вот замена
            classification = classification or fields["classification_level"]
            masked_title = masked_title or fields["masked_title"]
            if masked_details is None:
                masked_details = fields["masked_details"]

        _set_value(item, "classification_level", classification)
        _set_value(item, "masked_title", masked_title)
        _set_value(item, "masked_details", masked_details)

        author = _get_value(item, "author")
        author_email = _get_value(item, "author_email")
        if author_email is None and author is not None:
            author_email = _get_value(author, "email")

        _set_value(item, "author_email", author_email)
        _set_value(item, "display_title", masked_title or title)
        _set_value(item, "display_details", masked_details or details)
        return item

    def enrich_list(self, items: Sequence[Any]) -> list[Any]:
        """Применяет enrich ко всем элементам коллекции."""
        return [self.enrich(item) for item in items]

    def detect(self, text: str | None) -> str | None:
        """Определяет уровень секретности текста, возвращает наивысший найденный уровень."""
        if not text:
            return None
        text_lower = text.lower()
        for level in self.PRIORITY_ORDER:
            if level in text_lower:
                return level
        return None

    def mask(self, text: str | None) -> str | None:
        """Заменяет секретные фразы в тексте на нейтральные псевдонимы."""
        if not text:
            return text
        result = text
        for secret, replacement in sorted(
            self.REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True
        ):
            result = re.compile(re.escape(secret), re.IGNORECASE).sub(
                replacement, result
            )
        return result

    def build_document_fields(self, title: str, details: str | None) -> dict[str, Any]:
        """Возвращает поля классификации и маскировки для индексации
        в Elasticsearch (только при наличии секретных фраз)."""
        full_text = f"{title} {details}" if details else title
        classification = self.detect(full_text)

        if classification is None:
            return {
                "classification_level": None,
                "masked_title": None,
                "masked_details": None,
            }

        return {
            "classification_level": classification,
            "masked_title": self.mask(title),
            "masked_details": self.mask(details) if details else None,
        }

    def build_search_document(self, todo: Any) -> dict[str, Any]:
        """Формирует полный документ для индексации задачи в Elasticsearch."""
        fields = self.build_document_fields(
            _get_value(todo, "title"),
            _get_value(todo, "details"),
        )
        return {
            "todo_id": _get_value(todo, "id"),
            "author_id": _get_value(todo, "author_id"),
            "title": _get_value(todo, "title"),
            "details": _get_value(todo, "details"),
            "tag": _get_value(todo, "tag"),
            "created_at": _iso_format(_get_value(todo, "created_at")),
            "updated_at": _iso_format(_get_value(todo, "updated_at")),
            "updated_by": _get_value(todo, "updated_by"),
            "completed": _get_value(todo, "completed"),
            "completed_at": _iso_format(_get_value(todo, "completed_at")),
            **fields,
        }

    def merge_search_hits_with_todos(
        self,
        hits: Sequence[dict[str, Any]],
        todos: Sequence[Any],
    ) -> list[dict[str, Any]]:
        """Объединяет результаты поиска из Elasticsearch с данными из БД, обогащает для отображения."""
        todos_by_id = {str(_get_value(todo, "id")): todo for todo in todos}
        merged: list[dict[str, Any]] = []

        for hit in hits:
            todo_id = str(hit.get("todo_id"))
            todo = todos_by_id.get(todo_id)
            if todo is None:
                continue

            item = {
                "id": _get_value(todo, "id"),
                "author_id": _get_value(todo, "author_id"),
                "author_email": _get_value(_get_value(todo, "author"), "email"),
                "title": _get_value(todo, "title"),
                "details": _get_value(todo, "details"),
                "tag": _get_value(todo, "tag"),
                "completed": _get_value(todo, "completed"),
                "created_at": _get_value(todo, "created_at"),
                "completed_at": _get_value(todo, "completed_at"),
                "updated_at": _get_value(todo, "updated_at"),
                "updated_by": _get_value(todo, "updated_by"),
                "image_path": _get_value(todo, "image_path"),
                "_score": hit.get("_score"),
                "_id": hit.get("_id"),
                "highlight": hit.get("highlight"),
                "classification_level": hit.get("classification_level"),
                "masked_title": hit.get("masked_title"),
                "masked_details": hit.get("masked_details"),
            }
            merged.append(self.enrich(item))

        return merged
