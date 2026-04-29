import asyncio
import logging
import urllib.parse

import httpx

from app.adapters.base import PostItem, PostPage
from app.config import Settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_attempts: int,
    backoff_base: float,
) -> httpx.Response:
    """对 bridge/上游的间歇性 5xx、429 与网络类错误做有限次重试。"""
    max_attempts = max(1, max_attempts)
    for attempt in range(max_attempts):
        try:
            r = await client.get(url)
            r.raise_for_status()
            return r
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code not in _RETRYABLE_STATUS or attempt >= max_attempts - 1:
                raise
            delay = min(backoff_base * (2**attempt), 10.0)
            logger.warning(
                "douyin http %s for %s, retry in %.2fs (%s/%s)",
                code,
                url[:160],
                delay,
                attempt + 2,
                max_attempts,
            )
            await asyncio.sleep(delay)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            if attempt >= max_attempts - 1:
                raise
            delay = min(backoff_base * (2**attempt), 10.0)
            logger.warning(
                "douyin http %s for %s, retry in %.2fs (%s/%s)",
                type(e).__name__,
                url[:160],
                delay,
                attempt + 2,
                max_attempts,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("douyin http retry loop exited unexpectedly")


class HttpProxyDouyinAdapter:
    """对接自建 HTTP 服务（可由 Evil0ctal/Douyin_TikTok_Download_API 等二次封装暴露）。

    DOUYIN_HTTP_RESOLVE_URL 示例：`http://douyin-api:8000/internal/resolve?unique_id={unique_id}`
    响应 JSON：`{"sec_uid":"..."}`

    DOUYIN_HTTP_FEED_URL 示例：`http://douyin-api:8000/internal/user_posts?sec_uid={sec_uid}&cursor={cursor}`
    响应 JSON：`{"items":[{"aweme_id":"...","share_url":"..."}],"next_cursor":"...","has_more":true}`
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if not settings.douyin_http_resolve_url or not settings.douyin_http_feed_url:
            raise ValueError("DOUYIN_HTTP_RESOLVE_URL and DOUYIN_HTTP_FEED_URL are required for http adapter")

    async def resolve_sec_uid(self, unique_id: str) -> str:
        url = self._settings.douyin_http_resolve_url.format(unique_id=urllib.parse.quote(unique_id, safe=""))
        async with httpx.AsyncClient(timeout=self._settings.douyin_http_timeout_seconds) as client:
            r = await _get_with_retries(
                client,
                url,
                max_attempts=self._settings.douyin_http_max_attempts,
                backoff_base=self._settings.douyin_http_retry_backoff_base,
            )
            data = r.json()
        sec_uid = data.get("sec_uid")
        if not sec_uid or not isinstance(sec_uid, str):
            raise ValueError("resolve response missing sec_uid")
        return sec_uid

    async def fetch_user_post_page(self, sec_uid: str, cursor: str | None) -> PostPage:
        cur = cursor if cursor is not None else ""
        url = self._settings.douyin_http_feed_url.format(
            sec_uid=urllib.parse.quote(sec_uid, safe=""),
            cursor=urllib.parse.quote(cur, safe=""),
        )
        async with httpx.AsyncClient(timeout=self._settings.douyin_http_timeout_seconds) as client:
            r = await _get_with_retries(
                client,
                url,
                max_attempts=self._settings.douyin_http_max_attempts,
                backoff_base=self._settings.douyin_http_retry_backoff_base,
            )
            data = r.json()
        raw_items = data.get("items") or []
        items: list[PostItem] = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            aid = it.get("aweme_id")
            if not aid:
                continue
            aid_s = str(aid)
            surl = it.get("share_url")
            if not surl or not str(surl).strip():
                surl = f"https://www.douyin.com/video/{aid_s}"
            else:
                surl = str(surl).strip()
            items.append(PostItem(aweme_id=aid_s, share_url=surl))
        next_cursor = data.get("next_cursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            next_cursor = str(next_cursor) if next_cursor is not None else None
        has_more = bool(data.get("has_more", False))
        return PostPage(items=items, next_cursor=next_cursor, has_more=has_more)
