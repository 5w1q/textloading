import os
from urllib.parse import quote, urlparse

import httpx
from fastapi import HTTPException, Request


def _ab_base_url() -> str:
    return os.getenv("AB_BASE_URL", "http://127.0.0.1:3847").rstrip("/")


def _ab_login_path() -> str:
    return os.getenv("AB_LOGIN_PATH", "/login.html")


def _ab_app_id() -> str:
    return os.getenv("AB_APP_ID", "textloading").strip() or "textloading"


def _ab_timeout_sec() -> float:
    try:
        return max(3.0, float(os.getenv("AB_TIMEOUT_SEC", "20")))
    except ValueError:
        return 20.0


def _sync_cost() -> int:
    raw = os.getenv("AB_CREDITS_COST_SYNC", "3").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def _cookie_header_from_request(request: Request) -> str:
    return request.headers.get("cookie", "")


def _local_next_path(next_url: str) -> str:
    try:
        parsed = urlparse(next_url or "")
        if parsed.scheme or parsed.netloc:
            return "/"
        path = parsed.path or "/"
        if not path.startswith("/") or path.startswith("//"):
            return "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path
    except Exception:
        return "/"


def build_ab_login_url(next_url: str = "/", mode: str = "login") -> str:
    base = _ab_base_url()
    login_path = _ab_login_path()
    safe_next = _local_next_path(next_url)
    mode_q = "&mode=register" if mode == "register" else ""
    return f"{base}{login_path}?next={quote(safe_next, safe='/%?=&')}{mode_q}"


async def _ab_get(path: str, cookie_header: str) -> dict:
    async with httpx.AsyncClient(timeout=_ab_timeout_sec()) as client:
        res = await client.get(
            f"{_ab_base_url()}{path}",
            headers={"Cookie": cookie_header, "Accept": "application/json"},
        )
    try:
        data = res.json()
    except Exception:
        data = {}
    if res.status_code == 401:
        raise HTTPException(status_code=401, detail="请先登录 Ab 主站")
    if not res.is_success:
        msg = data.get("error") if isinstance(data, dict) else None
        raise HTTPException(status_code=502, detail=msg or f"主站接口异常: {res.status_code}")
    return data if isinstance(data, dict) else {}


async def get_ab_user_from_request(request: Request) -> dict:
    cookie_header = _cookie_header_from_request(request)
    if not cookie_header:
        raise HTTPException(status_code=401, detail="请先登录 Ab 主站")

    me_data = await _ab_get("/api/auth/me", cookie_header)
    summary_data = await _ab_get("/api/account/summary", cookie_header)

    if not me_data.get("ok") or not summary_data.get("ok"):
        raise HTTPException(status_code=502, detail="主站账户状态读取失败")

    user = me_data.get("user") or {}
    return {
        "id": user.get("id"),
        "email": user.get("email") or user.get("username") or "",
        "username": user.get("username") or "",
        "display_name": user.get("display_name") or "",
        "is_vip": bool(summary_data.get("is_member")),
        "membership_until": summary_data.get("membership_until"),
        "credits": int(summary_data.get("credits") or 0),
    }


async def try_consume_sync_from_request(request: Request, task_id: str) -> dict:
    cookie_header = _cookie_header_from_request(request)
    if not cookie_header:
        raise HTTPException(status_code=401, detail="请先登录 Ab 主站")

    payload = {
        "app_id": _ab_app_id(),
        "idempotency_key": f"{_ab_app_id()}:sync:{task_id}",
        "credits_cost": _sync_cost(),
    }
    async with httpx.AsyncClient(timeout=_ab_timeout_sec()) as client:
        res = await client.post(
            f"{_ab_base_url()}/api/account/try-consume",
            json=payload,
            headers={"Cookie": cookie_header, "Content-Type": "application/json"},
        )

    try:
        data = res.json()
    except Exception:
        data = {}

    if res.status_code == 401:
        raise HTTPException(status_code=401, detail="请先登录 Ab 主站")
    if not res.is_success:
        msg = data.get("error") if isinstance(data, dict) else None
        raise HTTPException(status_code=502, detail=msg or "主站扣费服务不可用")
    return data if isinstance(data, dict) else {}


async def proxy_ab_logout(request: Request) -> None:
    cookie_header = _cookie_header_from_request(request)
    if not cookie_header:
        return
    async with httpx.AsyncClient(timeout=_ab_timeout_sec()) as client:
        await client.post(
            f"{_ab_base_url()}/api/auth/logout",
            headers={"Cookie": cookie_header, "Accept": "application/json"},
        )
