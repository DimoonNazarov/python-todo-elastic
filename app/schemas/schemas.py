from enum import Enum
from datetime import datetime
from pydantic import BaseModel, model_validator
from pydantic import Field


class TodoSource(str, Enum):
    created = "Созданная"
    generated = "Сгенерированная"
    imported = "Импортированная"


class Tags(str, Enum):
    study = "Учёба"
    personal = "Личное"
    plans = "Планы"


class Todo(BaseModel):
    id: int | None = Field(default=None, alias="id")
    title: str = Field(min_length=3, max_length=200, default="Задача")
    details: str = Field(max_length=1000, default="Описание задачи")
    completed: bool = Field(default=False)
    tag: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    due_at: datetime | None = Field(default=None)
    source: TodoSource = Field(default=TodoSource.created)
    image_path: str | None = Field(default=None)
    image_hash: str | None = Field(default=None)
    details_hash: str | None = Field(default=None)
    spacy_summary: str | None = Field(default=None)
    llm_summary: str | None = Field(default=None)

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


class TodoDisplaySchema(BaseModel):
    id: int
    title: str
    details: str | None = None
    masked_title: str | None = None
    masked_details: str | None = None
    classification_level: str | None = None
    author_id: int
    author_email: str | None = None
    tag: str | None = None
    completed: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    image_path: str | None = None

    # только для фронта, не сериализуются обратно в БД
    display_title: str = Field(default="", exclude=False)
    display_details: str | None = Field(default=None, exclude=False)

    @model_validator(mode="after")
    def fill_display_fields(self) -> "TodoDisplaySchema":
        # Если masked поля не пришли — вычисляем на лету
        from app.services.search_index import TodoClassificationService

        svc = TodoClassificationService()

        if self.classification_level is None and self.masked_title is None:
            fields = svc.build_document_fields(self.title, self.details)
            self.classification_level = fields["classification_level"]
            self.masked_title = fields["masked_title"]
            self.masked_details = fields["masked_details"]

        self.display_title = self.masked_title or self.title
        self.display_details = self.masked_details or self.details
        return self

    model_config = {"from_attributes": True}
