from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    todo_id: Mapped[int] = mapped_column(ForeignKey("todos.id"), nullable=False)
    comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # "mention" | "reply" | "deadline"
    is_read: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    recipient = relationship("User", back_populates="notifications")
    todo = relationship("Todo")
    comment = relationship("Comment", back_populates="notifications")
