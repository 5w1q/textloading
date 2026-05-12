from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://douyin:douyin@localhost:5432/textloading_app"
    redis_url: str = "redis://localhost:6379/2"
    #: 共用 Redis 实例时的 key 前缀（与 Ab 的 REDIS_PREFIX 同角色；可读 REDIS_KEY_PREFIX 或 REDIS_PREFIX）
    redis_key_prefix: str = Field(
        default="",
        validation_alias=AliasChoices("REDIS_KEY_PREFIX", "REDIS_PREFIX"),
    )
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    #: 与 Ab 统一登录时须与 Ab 的 JWT_SECRET 完全一致；浏览器可带 Ab 的 httpOnly Cookie（默认名 ab_token）
    ab_auth_cookie_name: str = "ab_token"

    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    douyin_adapter: str = "mock"
    douyin_http_timeout_seconds: float = 30.0
    douyin_http_resolve_url: str = ""
    douyin_http_feed_url: str = ""
    #: bridge/上游偶发 502/503/504/429 时，对单次 GET 的最大尝试次数（含首次）
    douyin_http_max_attempts: int = 5
    #: 首次重试前等待秒数，之后指数退避，单次上限 10s
    douyin_http_retry_backoff_base: float = 0.5

    max_new_links_per_task: int = 100

    # --- 高并发 / 资源隔离 ---
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # 每用户每分钟最多创建多少个「同步任务」（多 API 实例共享 Redis）
    rate_limit_sync_per_user_per_minute: int = 30

    # 全集群同时访问抖音接口（resolve + 每一页 feed）的最大并发
    douyin_fetch_max_concurrent: int = 8

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
