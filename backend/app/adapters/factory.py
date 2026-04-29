from app.adapters.http_proxy import HttpProxyDouyinAdapter
from app.adapters.mock import MockDouyinAdapter
from app.config import Settings, get_settings


def get_douyin_adapter(settings: Settings | None = None):
    settings = settings or get_settings()
    name = (settings.douyin_adapter or "mock").lower().strip()
    if name == "http":
        return HttpProxyDouyinAdapter(settings)
    return MockDouyinAdapter()
