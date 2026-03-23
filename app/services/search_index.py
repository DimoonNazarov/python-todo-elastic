import re
from collections.abc import Mapping, Sequence
from typing import Any


SECRET_CLASSIFICATIONS = [
    "секретно",
    "совершенно секретно",
    "особой важности",
    "для служебного пользования",
    "конфиденциально",
    "дсп",
]

CLASSIFICATION_REPLACEMENTS = {
    "особой важности": "не интересссно",
    "совершенно секретно": "не интерессно",
    "для служебного пользования": "не интересно",
    "конфиденциально": "не интересно",
    "секретно": "не интересно",
    "дсп": "не интересно",
}

RUSSIAN_STOPWORDS = [
    "и",
    "в",
    "во",
    "не",
    "что",
    "он",
    "на",
    "я",
    "с",
    "со",
    "как",
    "а",
    "то",
    "все",
    "она",
    "так",
    "его",
    "но",
    "да",
    "ты",
    "к",
    "у",
    "же",
    "вы",
    "за",
    "бы",
    "по",
    "только",
    "ее",
    "мне",
    "было",
    "вот",
    "от",
    "меня",
    "еще",
    "нет",
    "о",
    "из",
    "ему",
    "теперь",
    "когда",
    "даже",
    "ну",
    "вдруг",
    "ли",
    "если",
    "уже",
    "или",
    "ни",
    "быть",
    "был",
    "него",
    "до",
    "вас",
    "нибудь",
    "опять",
    "уж",
    "вам",
    "ведь",
    "там",
    "потом",
    "себя",
    "ничего",
    "ей",
    "может",
    "они",
    "тут",
    "где",
    "есть",
    "надо",
    "ней",
    "для",
    "мы",
    "тебя",
    "их",
    "чем",
    "была",
    "сам",
    "чтоб",
    "без",
    "будто",
    "чего",
    "раз",
    "тоже",
    "себе",
    "под",
    "будет",
    "ж",
    "тогда",
    "кто",
    "этот",
    "того",
    "потому",
    "этого",
    "какой",
    "совсем",
    "ним",
    "здесь",
    "этом",
    "один",
    "почти",
    "мой",
    "тем",
    "чтобы",
    "нее",
    "сейчас",
    "были",
    "куда",
    "зачем",
    "сказать",
    "всех",
    "никогда",
    "сегодня",
    "можно",
    "при",
    "наконец",
    "два",
    "об",
    "другой",
    "хоть",
    "после",
    "над",
    "больше",
    "тот",
    "через",
    "эти",
    "нас",
    "про",
    "всего",
    "них",
    "какая",
    "много",
    "разве",
    "три",
    "эту",
    "моя",
    "впрочем",
    "хорошо",
    "свою",
    "этой",
    "перед",
    "иногда",
    "лучше",
    "чуть",
    "том",
    "нельзя",
    "такой",
    "им",
    "более",
    "всегда",
    "конечно",
    "всю",
    "между",
]

GROUP_NAMES = ["Александр", "Екатерина", "Дмитрий"]
ALL_STOPWORDS = RUSSIAN_STOPWORDS + [name.lower() for name in GROUP_NAMES]


def _get_value(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def _set_value(item: Any, field: str, value: Any) -> Any:
    if isinstance(item, Mapping):
        item[field] = value
    else:
        setattr(item, field, value)
    return item


def detect_classification(text: str | None) -> str | None:
    if not text:
        return None

    text_lower = text.lower()
    if "особой важности" in text_lower:
        return "особой важности"
    if "совершенно секретно" in text_lower:
        return "совершенно секретно"
    if "для служебного пользования" in text_lower or "дсп" in text_lower:
        return "дсп"
    if "конфиденциально" in text_lower:
        return "конфиденциально"
    if "секретно" in text_lower:
        return "секретно"
    return None


def mask_classification(text: str | None, classification: str | None = None) -> str | None:
    if not text:
        return text

    result = text
    for secret, replacement in sorted(
        CLASSIFICATION_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True
    ):
        pattern = re.compile(re.escape(secret), re.IGNORECASE)
        result = pattern.sub(replacement, result)
    return result


def build_masked_fields(title: str, details: str | None) -> dict[str, Any]:
    full_text = f"{title} {details}" if details else title
    classification = detect_classification(full_text)
    return {
        "classification_level": classification,
        "masked_title": mask_classification(title, classification) if classification else title,
        "masked_details": (
            mask_classification(details, classification) if classification and details else details
        ),
    }


def build_search_document(todo: Any) -> dict[str, Any]:
    masked = build_masked_fields(_get_value(todo, "title"), _get_value(todo, "details"))
    return {
        "todo_id": _get_value(todo, "id"),
        "title": _get_value(todo, "title"),
        "details": _get_value(todo, "details"),
        "tag": _get_value(todo, "tag"),
        "created_at": _isoformat(_get_value(todo, "created_at")),
        "updated_at": _isoformat(_get_value(todo, "updated_at")),
        "updated_by": _get_value(todo, "updated_by"),
        "completed": _get_value(todo, "completed"),
        "completed_at": _isoformat(_get_value(todo, "completed_at")),
        "classification_level": masked["classification_level"],
        "masked_title": masked["masked_title"],
        "masked_details": masked["masked_details"],
    }


def enrich_todo_display(item: Any) -> Any:
    title = _get_value(item, "title")
    details = _get_value(item, "details")
    masked_title = _get_value(item, "masked_title")
    masked_details = _get_value(item, "masked_details")
    classification = _get_value(item, "classification_level")

    if not classification or masked_title is None:
        masked = build_masked_fields(title, details)
        classification = classification or masked["classification_level"]
        masked_title = masked_title or masked["masked_title"]
        if masked_details is None:
            masked_details = masked["masked_details"]

    _set_value(item, "classification_level", classification)
    _set_value(item, "masked_title", masked_title)
    _set_value(item, "masked_details", masked_details)
    _set_value(item, "display_title", masked_title or title)
    _set_value(item, "display_details", masked_details or details)
    return item


def enrich_todo_display_list(items: Sequence[Any]) -> list[Any]:
    return [enrich_todo_display(item) for item in items]


def merge_search_hits_with_todos(hits: Sequence[dict[str, Any]], todos: Sequence[Any]) -> list[dict[str, Any]]:
    todos_by_id = {_get_value(todo, "id"): todo for todo in todos}
    merged: list[dict[str, Any]] = []

    for hit in hits:
        todo_id = hit.get("todo_id")
        todo = todos_by_id.get(todo_id)
        if todo is None:
            continue

        item = {
            "id": _get_value(todo, "id"),
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
        merged.append(enrich_todo_display(item))

    return merged


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if value else None
