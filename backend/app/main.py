from contextlib import asynccontextmanager

import redis.asyncio as redis_async
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.douyin_pool import init_douyin_permit_pool
from app.routers import auth, tasks, videos

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.redis_cli = redis_async.from_url(settings.redis_url, decode_responses=True)
    await init_douyin_permit_pool(app.state.redis_cli, settings.douyin_fetch_max_concurrent)
    app.state.redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.redis_pool.close(close_connection_pool=True)
    await app.state.redis_cli.aclose()


app = FastAPI(title="Douyin sync API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(videos.router)


@app.get("/config/public")
async def public_config() -> dict:
    """无需登录：告知当前是否为演示数据源，避免与真实抖音混淆。"""
    s = get_settings()
    adapter = (s.douyin_adapter or "mock").lower().strip()
    demo = adapter == "mock"
    return {
        "douyin_adapter": adapter,
        "max_new_links_per_task": s.max_new_links_per_task,
        "demo_mode": demo,
        "demo_explain": (
            "当前为 Mock 演示模式：不会请求抖音服务器，作品数量与链接均为本地生成的假数据，"
            "与输入的抖音号无关；链接无法在抖音 App/网页打开。"
            "需要真实数据请在服务端设置 DOUYIN_ADAPTER=http 并接入自建解析接口。"
            if demo
            else ""
        ),
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(response: Response) -> dict[str, str]:
    """就绪探针：检查 Redis（编排系统可据此摘流）。"""
    try:
        await app.state.redis_cli.ping()
    except Exception:  # noqa: BLE001
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ok"}
