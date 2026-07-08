from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from typing import Optional
import enum

from .base import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.EDITOR, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    # Todos созданные пользователем
    todos = relationship(
        "Todo",
        foreign_keys="[Todo.author_id]",  # Явно указываем поле
        back_populates="author",
        cascade="all, delete-orphan",
    )

    # Todos обновленные пользователем (НОВОЕ)
    updated_todos = relationship(
        "Todo",
        foreign_keys="[Todo.updated_by]",  # Явно указываем поле
        back_populates="updated_by_user",
        cascade="all, delete-orphan",
    )

    todo_edit_history = relationship(
        "TodoEditHistory",
        foreign_keys="[TodoEditHistory.editor_id]",
        back_populates="editor",
    )

    comments = relationship(
        "Comment",
        back_populates="author",
        cascade="all, delete-orphan",
    )

    notifications = relationship(
        "Notification",
        foreign_keys="[Notification.recipient_id]",
        back_populates="recipient",
        cascade="all, delete-orphan",
    )
