from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_PG_FROM_DOCKER_HINT = (
    "PostgreSQL 连接超时或失败。若 DATABASE_URL 使用 host.docker.internal："
    "宿主 Postgres 的 listen_addresses 不能只监听 127.0.0.1（建议 '*' 或包含 docker0 网段）；"
    "并在 pg_hba.conf 中为 Docker 网桥地址授权（常见如 host all all 172.17.0.0/16 scram-sha-256）。"
    "也可暂时改用 @postgres 指向 compose 内置库验证链路。"
)

settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    connect_args={"timeout": 25},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    try:
        async with engine.begin() as conn:
            await _init_db_schema(conn)
    except TimeoutError as e:
        raise RuntimeError(_PG_FROM_DOCKER_HINT) from e


async def _init_db_schema(conn) -> None:
    from app.models import Base

    await conn.run_sync(Base.metadata.create_all)
    if conn.dialect.name == "postgresql":
        # 多 Uvicorn worker 并发 startup 时，裸 CREATE INDEX IF NOT EXISTS 仍可能撞 pg_class 唯一约束
        await conn.execute(text("SELECT pg_advisory_xact_lock(872365412)"))
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_active_user_unique
                ON sync_tasks (user_id, unique_id)
                WHERE status IN ('pending', 'running');
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE user_videos
                ADD COLUMN IF NOT EXISTS source_task_id UUID NULL
                REFERENCES sync_tasks(id) ON DELETE SET NULL;
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_videos_source_task_id ON user_videos (source_task_id);"
            )
        )
