from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth as auth_service
from app.auth import create_access_token
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import TokenResponse, UserCreate, UserLogin, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserPublic)
async def me(current: User = Depends(get_current_user)) -> User:
    """供前端路由守卫校验：Bearer 或 Ab Cookie「ab_token」。"""
    return current


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
