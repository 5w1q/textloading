from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.ab_client import build_ab_login_url, get_ab_user_from_request, proxy_ab_logout
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login_redirect(next: str = "/"):
    return RedirectResponse(url=build_ab_login_url(next_url=next, mode="login"), status_code=307)


@router.get("/register")
async def register_redirect(next: str = "/"):
    return RedirectResponse(url=build_ab_login_url(next_url=next, mode="register"), status_code=307)


@router.get("/me")
async def get_me(request: Request, _: User = Depends(get_current_user)):
    # 复用主站会话信息，前端用于路由守卫
    me = await get_ab_user_from_request(request)
    return {"success": True, "data": me}


@router.post("/logout")
async def logout(request: Request):
    await proxy_ab_logout(request)
    return {"success": True}
