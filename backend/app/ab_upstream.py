"""从 Ab 主站 HTTP API 同步用户展示信息（JWT 内不含 display_name / 会员 / 积分）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.config import Settings

_log = logging.getLogger("uvicorn.error")


@dataclass
class AbHubProfile:
    display_name: str
    is_vip: bool
    points_remaining: int | None


async def fetch_ab_hub_profile(cookie_header: str | None, settings: Settings) -> AbHubProfile | None:
    """携带浏览器 Cookie 请求 Ab 的 /api/auth/me 与 /api/account/summary。"""
    if not cookie_header or f"{settings.ab_auth_cookie_name}=" not in cookie_header:
        return None
    origin = settings.ab_origin.rstrip("/")
    timeout = httpx.Timeout(settings.ab_upstream_timeout_seconds)
    headers = {"Cookie": cookie_header, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            me_res = await client.get(f"{origin}/api/auth/me", headers=headers)
            if me_res.status_code != 200:
                return None
            me_body = me_res.json()
            user = me_body.get("user") if isinstance(me_body, dict) else None
            if not isinstance(user, dict):
                return None

            email = user.get("email") or ""
            dn = user.get("display_name")
            if isinstance(dn, str) and dn.strip():
                display_name = dn.strip()
            elif isinstance(email, str) and email.strip():
                display_name = email.strip()
            else:
                display_name = ""

            credits: int | None = None
            is_vip = False
            sum_res = await client.get(f"{origin}/api/account/summary", headers=headers)
            if sum_res.status_code == 200:
                sj = sum_res.json()
                if isinstance(sj, dict):
                    raw_c = sj.get("credits")
                    if raw_c is not None:
                        try:
                            credits = int(raw_c)
                        except (TypeError, ValueError):
                            credits = None
                    is_vip = bool(sj.get("is_member"))

            return AbHubProfile(display_name=display_name, is_vip=is_vip, points_remaining=credits)
    except Exception as exc:
        _log.warning("Ab upstream profile fetch failed: %s", exc)
        return None


async def forward_ab_logout(cookie_header: str | None, settings: Settings) -> httpx.Response:
    origin = settings.ab_origin.rstrip("/")
    timeout = httpx.Timeout(settings.ab_upstream_timeout_seconds)
    headers = {"Cookie": cookie_header or "", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.post(f"{origin}/api/auth/logout", headers=headers)
