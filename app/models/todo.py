from datetime import datetime
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.orm import mapped_column
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.sql import func

from app.schemas import TodoSource
from .base import Base


class Todo(Base):
    """Todo model"""

    __tablename__ = "todos"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    details: Mapped[str] = mapped_column(nullable=False)
    completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    tag: Mapped[str | None] = mapped_column(nullable=True, default=None)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Кем и когда изменено
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source: Mapped[str] = mapped_column(nullable=False, default=TodoSource.created)
    image_path: Mapped[str | None] = mapped_column(nullable=True, default=None)
    image_hash: Mapped[str | None] = mapped_column(nullable=True, default=None)
    details_hash: Mapped[str | None] = mapped_column(nullable=True, default=None)
    spacy_summary: Mapped[str | None] = mapped_column(nullable=True, default=None)
    llm_summary: Mapped[str | None] = mapped_column(nullable=True, default=None)

    author = relationship(
        "User", foreign_keys=[author_id], back_populates="todos"  # Явно указываем
    )

    updated_by_user = relationship(
        "User",
        foreign_keys=[updated_by],  # Явно указываем
        back_populates="updated_todos",
    )

    def __repr__(self):
        return f"<Todo {self.id}>"
