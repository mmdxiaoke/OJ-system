"""Step 4：用户管理接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.deps import get_current_user, require_admin
from backend.core.request import query_param, read_json_body
from backend.core.responses import ApiError, ok
from backend.services import user_service

router = APIRouter(prefix="/api/users", tags=["users"])


def _body_field(body: dict, name: str) -> str:
    if name not in body:
        raise ApiError(400, f"field '{name}' is required")
    return body[name]


@router.post("/admin")
async def create_admin(request: Request, user: dict = Depends(require_admin)) -> dict:
    """创建管理员账户（仅管理员）。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    new_admin = await user_service.create_user(
        _body_field(body, "username"), _body_field(body, "password"), role="admin"
    )
    return ok("success", {"user_id": str(new_admin["user_id"]), "username": new_admin["username"]})


@router.post("/")
async def register(request: Request) -> dict:
    """用户注册（公开接口）。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    user = await user_service.create_user(_body_field(body, "username"), _body_field(body, "password"))
    return ok("register success", await user_service.public_user(user))


@router.get("/")
async def list_users(request: Request, user: dict = Depends(require_admin)) -> dict:
    """用户列表（仅管理员，支持分页）。"""
    page = query_param(request, "page")
    page_size = query_param(request, "page_size")
    total, users = await user_service.list_users(page, page_size)
    return ok("success", {"total": total, "users": await user_service.public_users(users)})


@router.get("/{user_id}")
async def get_user(user_id: str, user: dict = Depends(get_current_user)) -> dict:
    """查询用户信息（仅本人或管理员）。"""
    if user.get("role") != "admin" and str(user_id) != str(user["user_id"]):
        raise ApiError(403, "you can only view your own information")
    target = await user_service.get_user(user_id)
    if target is None:
        raise ApiError(404, "user not found")
    return ok("success", await user_service.public_user(target))


@router.put("/{user_id}/role")
async def update_role(user_id: str, request: Request, user: dict = Depends(require_admin)) -> dict:
    """变更用户权限（仅管理员）。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    role = _body_field(body, "role")
    target = await user_service.set_role(user_id, role)
    return ok("role updated", {"user_id": str(target["user_id"]), "role": target["role"]})
