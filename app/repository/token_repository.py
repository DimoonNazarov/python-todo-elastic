from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import CursorResult
from datetime import datetime, timezone

from app.models import RefreshToken


class TokenRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def find_by_token(self, refresh_token: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.refresh_token == refresh_token)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> list[RefreshToken]:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        return list(result.scalars().all())

    async def delete_by_token(self, refresh_token: str) -> bool:
        result = await self._session.execute(
            delete(RefreshToken).filter_by(refresh_token=refresh_token)
        )
        await self._session.flush()
        return result.rowcount > 0

    async def delete_by_user_id(self, user_id: int) -> int:
        result: CursorResult = await self._session.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        await self._session.flush()
        return result.rowcount or 0

    async def delete_expired(self) -> int:
        result: CursorResult = await self._session.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at < datetime.now(timezone.utc)
            )
        )
        await self._session.flush()
        return result.rowcount