from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class TodoEditHistory(Base):
    __tablename__ = "todo_edit_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    todo_id: Mapped[int] = mapped_column(ForeignKey("todos.id"), nullable=False)
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(nullable=False, default="edit")
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    title: Mapped[str] = mapped_column(nullable=False)
    details: Mapped[str] = mapped_column(nullable=False)
    tag: Mapped[str | None] = mapped_column(nullable=True, default=None)
    completed: Mapped[bool] = mapped_column(nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    image_path: Mapped[str | None] = mapped_column(nullable=True, default=None)
    spacy_summary: Mapped[str | None] = mapped_column(nullable=True, default=None)
    llm_summary: Mapped[str | None] = mapped_column(nullable=True, default=None)
    file_path: Mapped[str | None] = mapped_column(nullable=True, default=None)

    todo = relationship("Todo", back_populates="edit_history")
    editor = relationship("User", back_populates="todo_edit_history")
