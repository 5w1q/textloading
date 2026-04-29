from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ab_client import get_ab_user_from_request
from app.auth import get_user_by_id
from app.db import get_session
from app.models import User

async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """以 Ab 主站会话为准，按用户 ID 对齐本地用户实体。"""
    ab_user = await get_ab_user_from_request(request)
    user_id = ab_user.get("id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ab 登录态异常：缺少用户 ID",
        )
    user = await get_user_by_id(session, int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在，请先在 Ab 主站完成注册",
        )
    return user
