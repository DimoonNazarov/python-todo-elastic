import re
import logging
from sqlalchemy import select

from app.core.uow import UnitOfWork
from app.exceptions import NotFoundException, ForbiddenException
from app.models import Comment, Notification, User as UserORM
from app.schemas.comment import CommentCreate, CommentResponse, NotificationResponse
from app.schemas.user import SUserInfo

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"@([\w.+-]+@[\w.-]+\.\w+)")


class CommentService:
    async def get_comments(
        self,
        uow: UnitOfWork,
        todo_id: int,
    ) -> list[CommentResponse]:
        async with uow.start():
            comments = await uow.comment.get_by_todo_id(todo_id)
            return [CommentResponse.model_validate(c) for c in comments]

    async def create_comment(
        self,
        uow: UnitOfWork,
        todo_id: int,
        data: CommentCreate,
        current_user: SUserInfo,
    ) -> CommentResponse:
        async with uow.start():
            comment = Comment(
                todo_id=todo_id,
                author_id=current_user.id,
                parent_id=data.parent_id,
                content=data.content,
            )
            await uow.comment.add(comment)
            await uow.flush()

            await self._create_notifications(uow, comment, current_user)

            await uow.flush()
            refreshed = await uow.comment.get_by_id(comment.id)

        return CommentResponse.model_validate(refreshed)

    async def delete_comment(
        self,
        uow: UnitOfWork,
        todo_id: int,
        comment_id: int,
        current_user: SUserInfo,
    ) -> None:
        async with uow.start():
            comment = await uow.comment.get_by_id(comment_id)
            if not comment or comment.todo_id != todo_id:
                raise NotFoundException("Комментарий не найден")
            if comment.author_id != current_user.id and current_user.role != "admin":
                raise ForbiddenException("Нельзя удалять чужие комментарии")
            await uow.comment.soft_delete(comment_id)

    async def get_notifications(
        self,
        uow: UnitOfWork,
        current_user: SUserInfo,
    ) -> list[NotificationResponse]:
        async with uow.start():
            notifications = await uow.notification.get_all_for_user(current_user.id)
            return [self._to_notification_response(n) for n in notifications]

    async def mark_read(
        self,
        uow: UnitOfWork,
        notification_id: int,
        current_user: SUserInfo,
    ) -> None:
        async with uow.start():
            await uow.notification.mark_read(notification_id, current_user.id)

    async def mark_all_read(
        self,
        uow: UnitOfWork,
        current_user: SUserInfo,
    ) -> None:
        async with uow.start():
            await uow.notification.mark_all_read(current_user.id)

    async def count_unread(
        self,
        uow: UnitOfWork,
        current_user: SUserInfo,
    ) -> int:
        async with uow.start():
            return await uow.notification.count_unread(current_user.id)

    async def _create_notifications(
        self,
        uow: UnitOfWork,
        comment: Comment,
        author: SUserInfo,
    ) -> None:
        notified_ids: set[int] = set()

        # @mention уведомления
        emails = _MENTION_RE.findall(comment.content)
        for email in set(emails):
            if email == author.email:
                continue
            result = await uow._session.execute(
                select(UserORM).where(UserORM.email == email, UserORM.is_active == True)  # noqa: E712
            )
            user = result.scalar_one_or_none()
            if user and user.id not in notified_ids:
                notified_ids.add(user.id)
                n = Notification(
                    recipient_id=user.id,
                    todo_id=comment.todo_id,
                    comment_id=comment.id,
                    type="mention",
                )
                await uow.notification.add(n)

        # reply — уведомляем автора родительского комментария
        if comment.parent_id:
            parent = await uow.comment.get_by_id(comment.parent_id)
            if parent and parent.author_id != author.id and parent.author_id not in notified_ids:
                notified_ids.add(parent.author_id)
                n = Notification(
                    recipient_id=parent.author_id,
                    todo_id=comment.todo_id,
                    comment_id=comment.id,
                    type="reply",
                )
                await uow.notification.add(n)

    @staticmethod
    def _to_notification_response(n: Notification) -> NotificationResponse:
        return NotificationResponse(
            id=n.id,
            todo_id=n.todo_id,
            comment_id=n.comment_id,
            type=n.type,
            is_read=n.is_read,
            created_at=n.created_at,
            todo_title=n.todo.title if n.todo else None,
            comment_preview=(n.comment.content[:100] if n.comment and not n.comment.is_deleted else None),
            author_email=(n.comment.author.email if n.comment and n.comment.author else None),
        )
