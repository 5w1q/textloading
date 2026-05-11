"""跨进程、跨 Worker 限制同时访问抖音侧（解析/分页）的并发度，避免瞬时打爆风控。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _permits_redis_key() -> str:
    from app.config import get_settings

    p = get_settings().redis_key_prefix.strip().rstrip(":")
    tail = "douyin:fetch_permits"
    return f"{p}:{tail}" if p else tail

_INIT_LUA = """
local len = redis.call('LLEN', KEYS[1])
if len == 0 then
  local n = tonumber(ARGV[1])
  for i = 1, n do
    redis.call('LPUSH', KEYS[1], '1')
  end
end
return redis.call('LLEN', KEYS[1])
"""


async def init_douyin_permit_pool(redis: "Redis", pool_size: int) -> None:
    if pool_size <= 0:
        return
    await redis.eval(_INIT_LUA, 1, _permits_redis_key(), str(pool_size))


@asynccontextmanager
async def douyin_fetch_slot(redis: "Redis", wait_timeout: float = 120.0) -> AsyncIterator[None]:
    key = _permits_redis_key()
    popped = await redis.blpop(key, timeout=wait_timeout)
    if popped is None:
        raise TimeoutError("等待抖音抓取许可超时，请稍后重试")
    try:
        yield
    finally:
        await redis.lpush(key, "1")
