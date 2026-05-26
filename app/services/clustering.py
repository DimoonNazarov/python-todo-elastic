from __future__ import annotations

import logging
from collections.abc import Sequence

from app.models import Todo

logger = logging.getLogger(__name__)

RUSSIAN_STOP_WORDS = [
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
    "её",
    "мне",
    "было",
    "вот",
    "от",
    "меня",
    "ещё",
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
    "всех",
    "никогда",
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
    "задача",
    "описание",
    "нужно",
    "сделать",
    "это",
]


def cluster_todos(
    todos: Sequence[Todo],
    n_clusters: int = 3,
) -> list[dict]:
    """
    Кластеризует todos по тексту (title + details) через TF-IDF + KMeans.
    Возвращает список кластеров: [{"label": int, "todos": [...]}].
    """
    if len(todos) < 2:
        return [{"label": 0, "todos": list(todos)}] if todos else []

    try:
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        logger.error("scikit-learn не установлен")
        return [{"label": 0, "todos": list(todos)}]

    texts = [f"{t.title or ''} {t.details or ''}".strip() for t in todos]

    k = min(n_clusters, len(todos))

    vectorizer = TfidfVectorizer(
        stop_words=RUSSIAN_STOP_WORDS,
        max_features=1000,
        min_df=1,
    )
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return [{"label": 0, "todos": list(todos)}]

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(matrix)

    clusters: dict[int, list] = {i: [] for i in range(k)}
    for todo, label in zip(todos, labels):
        clusters[int(label)].append(todo)

    return [{"label": i + 1, "todos": clusters[i]} for i in range(k) if clusters[i]]
