"""Step 2：动态注册语言与查询语言列表。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.deps import get_current_user
from backend.core.request import read_json_body
from backend.core.responses import ApiError, ok
from backend.services import language_service

router = APIRouter(prefix="/api/languages", tags=["languages"])


@router.get("/")
async def list_languages() -> dict:
    """查询当前系统支持的所有语言。"""
    return ok("success", {"name": await language_service.language_names()})


@router.post("/")
async def register_language(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """动态注册新语言（所有已登录用户）。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    for field in ("name", "file_ext", "run_cmd"):
        if field not in body:
            raise ApiError(400, f"field '{field}' is required")
    lang = await language_service.register_language(body)
    return ok("language registered", {"name": lang["name"]})
