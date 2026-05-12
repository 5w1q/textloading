import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token_payload(token: str) -> dict | None:
    """校验 JWT，返回 payload（Ab：id/email/username；本站旧 token：sub）。"""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def decode_user_id(token: str) -> int | None:
    payload = decode_access_token_payload(token)
    if payload is None:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None


async def get_or_create_user_by_email(session: AsyncSession, email: str) -> User:
    norm = email.strip()
    existing = await get_user_by_email(session, norm)
    if existing is not None:
        return existing
    user = User(email=norm, hashed_password=hash_password(secrets.token_urlsafe(32)))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def ab_profile_from_claims(payload: dict, fallback_email: str) -> dict:
    """从 Ab JWT 里尽量取出展示用字段；字段名多种写法兼容，缺失则用默认值。"""
    flat = dict(payload)
    nested = payload.get("user")
    if isinstance(nested, dict):
        for k, v in nested.items():
            flat.setdefault(k, v)

    email = (fallback_email or "").strip()

    display = ""
    for key in ("nickname", "nick_name", "custom_username", "display_name", "name"):
        raw = flat.get(key)
        if isinstance(raw, str) and raw.strip():
            display = raw.strip()
            break
    if not display:
        pe = flat.get("email")
        if isinstance(pe, str) and pe.strip():
            display = pe.strip()
    if not display:
        display = email

    is_vip = False
    for key in ("is_vip", "vip"):
        raw = flat.get(key)
        if isinstance(raw, bool):
            is_vip = raw
            break
        if isinstance(raw, (int, float)):
            is_vip = raw != 0
            break
        if isinstance(raw, str) and raw.strip().lower() in ("1", "true", "yes", "vip"):
            is_vip = True
            break
    if not is_vip:
        vl = flat.get("vip_level")
        if isinstance(vl, (int, float)):
            is_vip = vl > 0
        elif isinstance(vl, str) and vl.strip().isdigit():
            is_vip = int(vl.strip()) > 0

    points_remaining: int | None = None
    for key in ("points", "credits", "balance", "score", "remaining_points", "points_remaining"):
        raw = flat.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            points_remaining = int(raw)
            break
        if isinstance(raw, str):
            s = raw.strip()
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                points_remaining = int(s)
                break

    return {
        "display_name": display,
        "is_vip": is_vip,
        "points_remaining": points_remaining,
    }


async def resolve_user_from_token_payload(session: AsyncSession, payload: dict) -> User | None:
    """Ab JWT 含 email/username；本站自建 JWT 仅含 sub。"""
    email_or_login = payload.get("email") or payload.get("username")
    if email_or_login:
        return await get_or_create_user_by_email(session, str(email_or_login))
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        uid = int(sub)
    except (TypeError, ValueError):
        return None
    return await get_user_by_id(session, uid)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
