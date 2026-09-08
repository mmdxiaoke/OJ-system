"""FastAPI 依赖：会话解析与权限校验。

注意：所有权限判断都在后端完成，前端的按钮隐藏只是体验优化。
由于使用 ``Depends``，鉴权会先于请求体校验执行，因此状态码优先级
401 > 403 > 400 能够自然满足。
"""
from __future__ import annotations

import time

from fastapi import Request

from backend import config
from backend.core import storage
from backend.core.responses import ApiError
from backend.services import user_service

PUBLIC_USER_FIELDS = ("user_id", "username", "role", "join_time")


async def _resolve_session(request: Request) -> dict | None:
    session_id = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not session_id:
        return None
    data = await storage.sessions_store.read()
    session = data.get("sessions", {}).get(session_id)
    if not session:
        return None
    if time.time() - float(session.get("created_at", 0)) > config.SESSION_TTL_SECONDS:
        await drop_session(session_id)
        return None
    user = await user_service.get_user(session.get("user_id"))
    if user is None:
        await drop_session(session_id)
        return None
    return user


async def get_optional_user(request: Request) -> dict | None:
    """未登录返回 None，不抛异常。"""
    user = await _resolve_session(request)
    if user is not None and user.get("role") == "banned":
        raise ApiError(403, "user is banned")
    return user


async def get_current_user(request: Request) -> dict:
    user = await _resolve_session(request)
    if user is None:
        raise ApiError(401, "not logged in")
    if user.get("role") == "banned":
        raise ApiError(403, "user is banned")
    return user


async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise ApiError(403, "admin privilege required")
    return user


async def create_session(user: dict) -> str:
    from backend.core.security import new_session_id

    session_id = new_session_id()
    record = {"user_id": str(user["user_id"]), "created_at": time.time()}

    def mutate(data: dict) -> dict:
        sessions = data.setdefault("sessions", {})
        # 清理过期会话，避免文件无限增长
        now = time.time()
        for sid in list(sessions):
            if now - float(sessions[sid].get("created_at", 0)) > config.SESSION_TTL_SECONDS:
                sessions.pop(sid, None)
        sessions[session_id] = record
        return data

    await storage.sessions_store.update(mutate)
    return session_id


async def drop_session(session_id: str | None) -> None:
    if not session_id:
        return

    def mutate(data: dict) -> dict:
        data.setdefault("sessions", {}).pop(session_id, None)
        return data

    await storage.sessions_store.update(mutate)


async def drop_sessions_of_user(user_id: str) -> None:
    def mutate(data: dict) -> dict:
        sessions = data.setdefault("sessions", {})
        for sid in [s for s, v in sessions.items() if str(v.get("user_id")) == str(user_id)]:
            sessions.pop(sid, None)
        return data

    await storage.sessions_store.update(mutate)


def current_session_id(request: Request) -> str | None:
    return request.cookies.get(config.SESSION_COOKIE_NAME)


def public_view(user: dict) -> dict:
    return {k: (str(user[k]) if k == "user_id" else user.get(k)) for k in PUBLIC_USER_FIELDS}


def is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") == "admin"
