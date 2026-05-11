"""基于 Redis 的固定窗口限流（多 API 实例安全）。"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _rate_limit_key(user_id: int, window: int) -> str:
    from app.config import get_settings

    p = get_settings().redis_key_prefix.strip().rstrip(":")
    tail = f"rl:sync:user:{user_id}:{window}"
    return f"{p}:{tail}" if p else tail


async def check_user_sync_rate_limit(redis: "Redis", user_id: int, max_per_minute: int) -> None:
    if max_per_minute <= 0:
        return
    window = int(time.time() // 60)
    key = _rate_limit_key(user_id, window)
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 120)
    if n > max_per_minute:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="同步请求过于频繁，请稍后再试",
        )
