from datetime import datetime
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.orm import mapped_column
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.sql import func

from app.schemas import Tags
from app.schemas import TodoSource
from .base import Base


class Todo(Base):
    """Todo model"""

    __tablename__ = "todos"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    details: Mapped[str] = mapped_column(nullable=False)
    completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    tag: Mapped[str] = mapped_column(default=Tags.plans, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(nullable=False, default=TodoSource.created)
    image_path: Mapped[str | None] = mapped_column(nullable=True, default=None)
    image_hash: Mapped[str | None] = mapped_column(nullable=True, default=None)

    author = relationship("User", back_populates="todos")

    def __repr__(self):
        return f"<Todo {self.id}>"
