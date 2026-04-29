"""
薄桥接：将 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)
的 Web API 映射为 textloading 的 HttpProxyDouyinAdapter 契约。

上游需自行部署；`UPSTREAM_BASE_URL` 指向单实例根地址，或多实例轮询时使用 `UPSTREAM_BASE_URLS`（逗号分隔，见 bridge/README.md）。
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Query


def _load_upstream_bases() -> list[str]:
    """
    多 Cookie = 多实例 Evil0ctal：用 UPSTREAM_BASE_URLS 逗号/分号分隔多个根地址，bridge 按请求轮询。
    未设置时回退到单个 UPSTREAM_BASE_URL。
    """
    raw = os.environ.get("UPSTREAM_BASE_URLS", "").strip()
    if raw:
        parts = [p.strip().rstrip("/") for p in re.split(r"[,;]", raw) if p.strip()]
        if parts:
            return parts
    single = os.environ.get("UPSTREAM_BASE_URL", "http://host.docker.internal:19001").rstrip("/")
    return [single]


UPSTREAM_LIST = _load_upstream_bases()
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "60"))
FEED_PAGE_SIZE = int(os.environ.get("BRIDGE_FEED_PAGE_SIZE", "20"))

_rr_lock = threading.Lock()
_rr_i = 0


def _next_upstream_base() -> str:
    if len(UPSTREAM_LIST) == 1:
        return UPSTREAM_LIST[0]
    global _rr_i
    with _rr_lock:
        base = UPSTREAM_LIST[_rr_i % len(UPSTREAM_LIST)]
        _rr_i += 1
        return base

SECUID_RE = re.compile(r"MS4wLj[A-Za-z0-9_\-+/=]+")

app = FastAPI(title="Douyin bridge for textloading", version="1.0.0")


def _find_sec_uid(obj: Any) -> str | None:
    if isinstance(obj, str):
        m = SECUID_RE.search(obj)
        return m.group(0) if m else None
    if isinstance(obj, dict):
        for k in ("sec_user_id", "sec_uid", "sec_userid"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("MS4wLj"):
                m = SECUID_RE.search(v)
                return m.group(0) if m else v
        for v in obj.values():
            r = _find_sec_uid(v)
            if r:
                return r
    if isinstance(obj, list):
        for x in obj:
            r = _find_sec_uid(x)
            if r:
                return r
    return None


def _unwrap_upstream_data(payload: dict[str, Any]) -> Any:
    """Evil0ctal ResponseModel: {code, router, data}."""
    c = payload.get("code")
    if c not in (200, "200", 0, "0", None):
        raise HTTPException(status_code=502, detail=f"upstream error: {payload}")
    return payload.get("data")


def _feed_root(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and "aweme_list" in data:
        return data
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and "aweme_list" in inner:
            return inner
    raise HTTPException(status_code=502, detail="upstream feed: missing aweme_list")


def _aweme_to_item(aweme: dict[str, Any]) -> dict[str, str] | None:
    aid = aweme.get("aweme_id") or aweme.get("aweme_id_str")
    if aid is None:
        return None
    aid_s = str(aid)
    share_info = aweme.get("share_info") or {}
    surl = share_info.get("share_url") if isinstance(share_info, dict) else None
    if not surl:
        surl = f"https://www.douyin.com/video/{aid_s}"
    return {"aweme_id": aid_s, "share_url": str(surl)}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "upstreams": UPSTREAM_LIST,
        "rotation": len(UPSTREAM_LIST) > 1,
    }


@app.get("/douyin/resolve")
async def resolve(unique_id: str = Query(..., min_length=1, description="抖音号 unique_id")):
    """
    映射上游: GET /api/douyin/web/get_sec_user_id?url=<抖音用户页>
    使用 https://www.douyin.com/user/{unique_id}（若该号仅移动端展示，可能需用户自行换可解析的主页 URL 规则）。
    """
    uid = unique_id.strip()
    user_url = f"https://www.douyin.com/user/{quote(uid, safe='')}"
    q = quote(user_url, safe="")
    base = _next_upstream_base()
    url = f"{base}/api/douyin/web/get_sec_user_id?url={q}"
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        r = await client.get(url)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"upstream HTTP {r.status_code}: {r.text[:500]}")
        payload = r.json()
    data = _unwrap_upstream_data(payload)
    sec = _find_sec_uid(data)
    if not sec:
        raise HTTPException(status_code=502, detail="could not parse sec_uid from upstream response")
    return {"sec_uid": sec}


@app.get("/douyin/feed")
async def feed(
    sec_uid: str = Query(..., min_length=8, description="等同上游 sec_user_id"),
    cursor: str = Query("", description="首次为空；否则为上一页 max_cursor"),
):
    """
    映射上游: GET /api/douyin/web/fetch_user_post_videos?sec_user_id=&max_cursor=&count=
    """
    try:
        max_cursor = int(cursor) if cursor.strip() != "" else 0
    except ValueError as e:
        raise HTTPException(status_code=400, detail="cursor must be int or empty") from e

    q_sec = quote(sec_uid.strip(), safe="")
    base = _next_upstream_base()
    url = (
        f"{base}/api/douyin/web/fetch_user_post_videos"
        f"?sec_user_id={q_sec}&max_cursor={max_cursor}&count={FEED_PAGE_SIZE}"
    )
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        r = await client.get(url)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"upstream HTTP {r.status_code}: {r.text[:500]}")
        payload = r.json()

    data = _unwrap_upstream_data(payload)
    root = _feed_root(data)
    aweme_list = root.get("aweme_list") or []
    items: list[dict[str, str]] = []
    for aweme in aweme_list:
        if not isinstance(aweme, dict):
            continue
        it = _aweme_to_item(aweme)
        if it:
            items.append(it)

    raw_next = root.get("max_cursor")
    next_cursor = "" if raw_next is None else str(raw_next)
    hm = root.get("has_more", 0)
    has_more = bool(hm) if not isinstance(hm, str) else hm.lower() in ("1", "true", "yes")

    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
