from elasticsearch import AsyncElasticsearch, NotFoundError
from typing import Optional, List
import logging
import re

from app.models import Todo

logger = logging.getLogger(__name__)

INDEX_NAME = "todos"

# Список грифов секретности для фильтрации
SECRET_CLASSIFICATIONS = [
    "секретно",
    "совершенно секретно",
    "особой важности",
    "для служебного пользования",
    "конфиденциально"
]

# Список стоп-слов русского языка
RUSSIAN_STOPWORDS = [
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет",
    "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже",
    "или", "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам",
    "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где",
    "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб",
    "без", "будто", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда",
    "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь",
    "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда",
    "зачем", "сказать", "всех", "никогда", "сегодня", "можно", "при", "наконец",
    "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через", "эти",
    "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя",
    "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том",
    "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между"
]

# Три имени из группы (замените на реальные имена вашей группы)
GROUP_NAMES = ["Александр", "Екатерина", "Дмитрий"]

# Объединяем стоп-слова с именами
ALL_STOPWORDS = RUSSIAN_STOPWORDS + [name.lower() for name in GROUP_NAMES]


def create_russian_analyzer_mapping():
    """Создает маппинг с русским анализатором и фильтрами"""
    return {
        "settings": {
            "analysis": {
                "analyzer": {
                    "russian_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "russian_stop",
                            "russian_stemmer"
                        ]
                    }
                },
                "filter": {
                    "russian_stop": {
                        "type": "stop",
                        "stopwords": ALL_STOPWORDS
                    },
                    "russian_stemmer": {
                        "type": "stemmer",
                        "language": "russian"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "todo_id": {"type": "integer"},
                "title": {
                    "type": "text",
                    "analyzer": "russian_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 256}
                    }
                },
                "details": {
                    "type": "text",
                    "analyzer": "russian_analyzer"
                },
                "tag": {"type": "keyword"},
                "created_at": {"type": "date"},
                "completed": {"type": "boolean"},
                "completed_at": {"type": "date"},
                "classification_level": {"type": "keyword"},  # Добавлено поле для уровня секретности
                "masked_title": {"type": "text"},  # Замаскированный заголовок
                "masked_details": {"type": "text"}  # Замаскированные детали
            }
        }
    }


def detect_classification(text: str) -> Optional[str]:
    """Определяет уровень секретности текста"""
    if not text:
        return None

    text_lower = text.lower()

    # Проверяем в порядке убывания важности
    if "особой важности" in text_lower:
        return "особой важности"
    elif "совершенно секретно" in text_lower:
        return "совершенно секретно"
    elif "секретно" in text_lower:
        return "секретно"
    elif "для служебного пользования" in text_lower or "дсп" in text_lower:
        return "дсп"
    elif "конфиденциально" in text_lower:
        return "конфиденциально"

    return None


def mask_classification(text: str, classification: str) -> str:
    """Заменяет грифы на соответствующие надписи"""
    if not text:
        return text

    replacements = {
        "секретно": "не интересно",
        "совершенно секретно": "не интерессно",
        "особой важности": "не интересссно",
        "для служебного пользования": "не интересно",
        "дсп": "не интересно",
        "конфиденциально": "не интересно"
    }

    result = text
    for secret, replacement in replacements.items():
        if secret in result.lower():
            # Заменяем с сохранением регистра первой буквы
            pattern = re.compile(re.escape(secret), re.IGNORECASE)
            result = pattern.sub(replacement, result)

    return result


class ElasticRepository:
    def __init__(self, client: AsyncElasticsearch):
        self._client = client

    async def ensure_index_exists(self):
        """Создает индекс с русским анализатором, если он еще не существует."""
        exists = await self._client.indices.exists(index=INDEX_NAME)
        if not exists:
            mapping = create_russian_analyzer_mapping()
            await self._client.indices.create(index=INDEX_NAME, body=mapping)
            logger.info("Index '%s' created with Russian analyzer.", INDEX_NAME)

    async def index_todo(self, todo: Todo):
        """Добавляет или обновляет документ задачи с учетом классификации."""
        try:
            # Объединяем текст для определения классификации
            full_text = f"{todo.title} {todo.details}" if todo.details else todo.title
            classification = detect_classification(full_text)

            # Подготавливаем документ
            document = {
                "todo_id": todo.id,
                "title": todo.title,
                "details": todo.details,
                "tag": todo.tag,
                "created_at": todo.created_at.isoformat() if todo.created_at else None,
                "completed": todo.completed,
                "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
                "classification_level": classification
            }

            # Если обнаружена классификация, добавляем замаскированные поля
            if classification:
                document["masked_title"] = mask_classification(todo.title, classification)
                document["masked_details"] = mask_classification(todo.details, classification) if todo.details else None
                logger.info(f"Todo {todo.id} has classification: {classification}")

            await self._client.index(
                index=INDEX_NAME,
                id=str(todo.id),
                document=document
            )
            logger.info(f"Successfully indexed todo {todo.id}")

        except Exception as e:
            logger.error("Failed to index todo %s: %s", todo.id, e)

    async def update_todo(self, todo_id: int, todo: Todo):
        """Частично обновляет документ задачи."""
        try:
            # Проверяем классификацию для обновленных полей
            full_text = f"{todo.title} {todo.details}" if todo.details else todo.title
            classification = detect_classification(full_text)

            doc_update = {
                "title": todo.title,
                "details": todo.details,
                "tag": todo.tag,
                "completed": todo.completed,
                "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
                "classification_level": classification
            }

            # Добавляем замаскированные поля при необходимости
            if classification:
                doc_update["masked_title"] = mask_classification(todo.title, classification)
                doc_update["masked_details"] = mask_classification(todo.details,
                                                                   classification) if todo.details else None

            await self._client.update(
                index=INDEX_NAME,
                id=str(todo_id),
                doc=doc_update
            )
            logger.info(f"Updated todo {todo_id} in index")

        except NotFoundError:
            logger.warning("Todo %s not found in index on update.", todo_id)

        except Exception as e:
            logger.error("Failed to update todo %s in index: %s", todo_id, e)

    async def delete_todo(self, todo_id: int):
        """Удаляет документ задачи из индекса."""
        try:
            await self._client.delete(index=INDEX_NAME, id=str(todo_id))
            logger.info(f"Deleted todo {todo_id} from index")
        except NotFoundError:
            logger.warning("Todo %s not found in index on delete.", todo_id)
        except Exception as e:
            logger.error("Failed to delete todo %s from index: %s", todo_id, e)

    async def search_todos(
            self,
            query_text: str,
            tag: Optional[str] = None,
            limit: int = 50,
            skip: int = 0
    ) -> List[dict]:
        """
        Полнотекстовый поиск по title и details с нестрогим соответствием.
        Использует русский анализатор для учета морфологии.
        """
        # Базовый запрос с нестрогим соответствием
        should_clauses = [
            {
                "match": {
                    "title": {
                        "query": query_text,
                        "fuzziness": "AUTO",  # Нечеткий поиск для опечаток
                        "operator": "or",
                        "minimum_should_match": "50%"
                    }
                }
            },
            {
                "match": {
                    "details": {
                        "query": query_text,
                        "fuzziness": "AUTO",
                        "operator": "or",
                        "minimum_should_match": "30%"
                    }
                }
            }
        ]

        # Добавляем поиск по замаскированным полям, если они есть
        should_clauses.extend([
            {
                "match": {
                    "masked_title": {
                        "query": query_text,
                        "fuzziness": "AUTO",
                        "operator": "or"
                    }
                }
            },
            {
                "match": {
                    "masked_details": {
                        "query": query_text,
                        "fuzziness": "AUTO",
                        "operator": "or"
                    }
                }
            }
        ])

        must_clauses = []
        if tag:
            must_clauses.append({"term": {"tag": tag}})

        try:
            # Убеждаемся, что индекс существует
            await self.ensure_index_exists()

            # Выполняем поиск
            response = await self._client.search(
                index=INDEX_NAME,
                body={
                    "from": skip,
                    "size": limit,
                    "query": {
                        "bool": {
                            "should": should_clauses,
                            "must": must_clauses,
                            "minimum_should_match": 1
                        }
                    },
                    "sort": [
                        {"_score": {"order": "desc"}},  # Сначала по релевантности
                        {"created_at": {"order": "desc"}}  # Потом по дате
                    ],
                    "highlight": {  # Подсветка совпадений
                        "fields": {
                            "title": {"number_of_fragments": 1},
                            "details": {"number_of_fragments": 2},
                            "masked_title": {"number_of_fragments": 1},
                            "masked_details": {"number_of_fragments": 2}
                        },
                        "pre_tags": ["<mark>"],
                        "post_tags": ["</mark>"]
                    }
                }
            )

            results = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                # Добавляем информацию о релевантности и подсветке
                result = {
                    **source,
                    "_score": hit["_score"],
                    "_id": hit["_id"],
                }
                if "highlight" in hit:
                    result["highlight"] = hit["highlight"]
                results.append(result)

            logger.info(f"Search for '{query_text}' found {len(results)} results")
            return results

        except Exception as e:
            logger.error("Search failed: %s", e)
            return []

    async def search_by_classification(self, classification: str, limit: int = 50) -> List[dict]:
        """Поиск тудушек по уровню секретности"""
        try:
            response = await self._client.search(
                index=INDEX_NAME,
                body={
                    "size": limit,
                    "query": {
                        "term": {"classification_level": classification}
                    },
                    "sort": [{"created_at": {"order": "desc"}}]
                }
            )
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Search by classification failed: {e}")
            return []

    async def get_statistics(self) -> dict:
        """Получает статистику по индексу"""
        try:
            # Подсчет документов по классификации
            agg_query = {
                "size": 0,
                "aggs": {
                    "by_classification": {
                        "terms": {"field": "classification_level"}
                    },
                    "by_tag": {
                        "terms": {"field": "tag"}
                    },
                    "total_count": {
                        "value_count": {"field": "todo_id"}
                    }
                }
            }

            response = await self._client.search(
                index=INDEX_NAME,
                body=agg_query
            )

            stats = {
                "total": response["hits"]["total"]["value"],
                "by_classification": {},
                "by_tag": {}
            }

            if "aggregations" in response:
                aggs = response["aggregations"]

                if "by_classification" in aggs:
                    for bucket in aggs["by_classification"]["buckets"]:
                        stats["by_classification"][bucket["key"]] = bucket["doc_count"]

                if "by_tag" in aggs:
                    for bucket in aggs["by_tag"]["buckets"]:
                        stats["by_tag"][bucket["key"]] = bucket["doc_count"]

            return stats

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}


    async def search_by_date(self, date_from: str) -> List[dict]:
        """Возвращает все тудушки, созданные после указанной даты"""
        try:
            response = await self._client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "range": {
                            "created_at": {
                                "gte": date_from
                            }
                        }
                    },
                    "sort": [{"created_at": {"order": "desc"}}]
                }
            )
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Failed to get search results: {e}")
            return []


    async def search_by_tag(self, tag: str) -> List[dict]:
        """Возвращает все тудушки с заданным тегом"""
        try:
            response = await self._client.search(
                index=INDEX_NAME,
                body={
                    "query": {
                        "term": {"tag": tag}
                    },
                    "sort": [{"created_at": {"order": "desc"}}]
                }
            )
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"Failed to get search results: {e}")
            return []
