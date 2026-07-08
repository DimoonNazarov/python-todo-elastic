from datetime import datetime
from pydantic import BaseModel, Field


class CommentAuthor(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str

    model_config = {"from_attributes": True}


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    parent_id: int | None = None


class CommentResponse(BaseModel):
    id: int
    todo_id: int
    author_id: int
    parent_id: int | None
    content: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime | None
    author: CommentAuthor
    replies: list["CommentResponse"] = []

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    id: int
    todo_id: int
    comment_id: int | None
    type: str
    is_read: bool
    created_at: datetime
    todo_title: str | None = None
    comment_preview: str | None = None
    author_email: str | None = None
    due_at: datetime | None = None

    model_config = {"from_attributes": True}
