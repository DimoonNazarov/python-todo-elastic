from enum import Enum
from datetime import datetime
from pydantic import BaseModel
from pydantic import Field
from typing import Optional


class TodoSource(str, Enum):
    created = "Созданная"
    generated = "Сгенерированная"
    imported = "Импортированная"


class Tags(str, Enum):
    study = "Учёба"
    personal = "Личное"
    plans = "Планы"


class Todo(BaseModel):
    id: Optional[int] = Field(default=None, alias="id")
    title: str = Field(min_length=3, max_length=200, default="Задача")
    details: str = Field(max_length=500, default="Описание задачи")
    completed: bool = Field(default=False)
    tag: Tags = Field(default=Tags.plans)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    source: TodoSource = Field(default=TodoSource.created)
    image_path: str | None = Field(default=None)
    image_hash: str | None = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "Задача",
                    "details": "Описание задачи",
                    "completed": False,
                    "tag": "Планы",
                    "created_at": "2023-10-01T00:00:00Z",
                    "completed_at": None,
                    "source": "Созданная",
                }
            ]
        }
    }
