from fastapi import Request, Depends, HTTPException
from typing import Annotated
from app.core import get_async_uow_session, UnitOfWork
from app.models import User as UserORM
from app.schemas import SUserInfo


async def get_current_user(request: Request) -> dict:
    payload = getattr(request.state, "user", None)
    if payload is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


async def get_optional_current_active_user(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
) -> SUserInfo | None:
    payload = getattr(request.state, "user", None)
    if payload is None:
        return None
    async with uow_session.start():
        user: UserORM = await uow_session.auth.find_one_or_none_by_id(int(payload["user_id"]))
        if not user or not user.is_active:
            return None
        return SUserInfo.model_validate(user)


async def get_current_active_user(
    payload: Annotated[dict, Depends(get_current_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
) -> SUserInfo:
    async with uow_session.start():
        user: UserORM = await uow_session.auth.find_one_or_none_by_id(int(payload["user_id"]))
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="Inactive user")
        return SUserInfo.model_validate(user)
