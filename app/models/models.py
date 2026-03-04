from datetime import datetime
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import DateTime
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(nullable=False, default=TodoSource.created)
    image_path: Mapped[str | None] = mapped_column(nullable=True, default=None)
    image_hash: Mapped[str | None] = mapped_column(nullable=True, default=None)

    def __repr__(self):
        return f"<Todo {self.id}>"


# class User(Base):
#     """Todo model"""
#
#     __tablename__ = "users"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     name: Mapped[str] = mapped_column(nullable=False)
#     password: Mapped[str] = mapped_column(nullable=False)
#     disabled: Mapped[bool] = mapped_column(nullable=False, default=False)
#
#     def __repr__(self):
#         return f"<User {self.id}>"
