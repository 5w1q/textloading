from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth as auth_service
from app.ab_upstream import fetch_ab_hub_profile, forward_ab_logout
from app.auth import create_access_token
from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import AuthMePublic, TokenResponse, UserCreate, UserLogin, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMePublic)
async def me(request: Request, current: User = Depends(get_current_user)) -> AuthMePublic:
    """校验登录；展示字段优先从 Ab 在线接口同步（与账号页一致），失败时再读 JWT claims。"""
    payload = getattr(request.state, "jwt_payload", None)
    if not isinstance(payload, dict):
        payload = {}
    settings = get_settings()
    synced = await fetch_ab_hub_profile(request.headers.get("cookie"), settings)
    if synced is not None:
        display_name = (synced.display_name or "").strip() or current.email
        return AuthMePublic(
            id=current.id,
            email=current.email,
            display_name=display_name,
            is_vip=synced.is_vip,
            points_remaining=synced.points_remaining,
        )
    profile = auth_service.ab_profile_from_claims(payload, current.email)
    return AuthMePublic(
        id=current.id,
        email=current.email,
        display_name=profile["display_name"],
        is_vip=profile["is_vip"],
        points_remaining=profile["points_remaining"],
    )


@router.post("/ab-logout")
async def ab_logout_proxy(request: Request) -> Response:
    """代理 Ab 登出：清除浏览器侧 ab_token（需在 Hub 同源调用以便带回 Set-Cookie）。"""
    settings = get_settings()
    try:
        r = await forward_ab_logout(request.headers.get("cookie"), settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Ab logout unreachable") from exc
    out = Response(content=r.content, status_code=r.status_code)
    ct = r.headers.get("content-type")
    if ct:
        out.headers["content-type"] = ct
    for key, value in r.headers.multi_items():
        if key.lower() == "set-cookie":
            out.headers.append("set-cookie", value)
    return out


@router.head("/me")
async def me_head(current: User = Depends(get_current_user)) -> Response:
    """与 GET 相同鉴权；便于 curl -I 等 HEAD 探针。"""
    return Response(status_code=status.HTTP_200_OK)


@router.post("/register", response_model=UserPublic)
async def register(body: UserCreate, session: AsyncSession = Depends(get_session)) -> User:
    existing = await auth_service.get_user_by_email(session, body.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=body.email, hashed_password=auth_service.hash_password(body.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    user = await auth_service.get_user_by_email(session, body.email)
    if user is None or not auth_service.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)
