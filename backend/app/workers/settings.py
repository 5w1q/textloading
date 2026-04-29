import os

from arq.connections import RedisSettings

from app.config import get_settings
from app.douyin_pool import init_douyin_permit_pool
from app.workers.sync_job import process_sync_task


async def startup(ctx: dict) -> None:
    import redis.asyncio as redis_async
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    ctx["redis_cli"] = redis_async.from_url(settings.redis_url, decode_responses=True)
    await init_douyin_permit_pool(ctx["redis_cli"], settings.douyin_fetch_max_concurrent)


async def shutdown(ctx: dict) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    r = ctx.get("redis_cli")
    if r is not None:
        await r.aclose()


class WorkerSettings:
    functions = [process_sync_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = int(os.environ.get("WORKER_MAX_JOBS", "8"))
    job_timeout = int(os.environ.get("WORKER_JOB_TIMEOUT", "900"))
