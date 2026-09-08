"""Step 4：登录 / 登出接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from backend import config
from backend.core.deps import create_session, current_session_id, drop_session, get_current_user
from backend.core.request import read_json_body
from backend.core.responses import ApiError, ok
from backend.services import user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=config.SESSION_HTTPS_ONLY,
        max_age=config.SESSION_TTL_SECONDS,
        path="/",
    )


@router.post("/login")
async def login(request: Request, response: Response) -> dict:
    """用户登录：校验密码 -> 创建服务端会话 -> 下发 Cookie。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    username = body.get("username")
    password = body.get("password")
    if username is None or password is None:
        raise ApiError(400, "fields 'username' and 'password' are required")

    user = await user_service.authenticate(username, password)
    session_id = await create_session(user)
    _set_session_cookie(response, session_id)
    return ok("login success", {
        "user_id": str(user["user_id"]),
        "username": user["username"],
        "role": user.get("role", "user"),
    })


@router.post("/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_current_user)) -> dict:
    """用户登出：清除服务端会话并删除 Cookie。"""
    await drop_session(current_session_id(request))
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    return ok("logout success", None)
