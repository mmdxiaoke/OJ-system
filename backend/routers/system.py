"""系统级接口：健康检查与测试用重置。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from backend import config
from backend.core import storage
from backend.core.deps import get_current_user
from backend.core.responses import ApiError, ok
from backend.services import (
    language_service,
    log_service,
    problem_service,
    submission_service,
    user_service,
)

router = APIRouter(tags=["system"])


async def _require_admin_or_test_mode(user: dict = Depends(get_current_user)) -> dict:
    """系统重置：默认仅管理员；OJ_RESET_OPEN=1 时放开（便于自动测试）。"""
    if os.environ.get("OJ_RESET_OPEN") == "1":
        return user
    if user.get("role") != "admin":
        raise ApiError(403, "admin privilege required")
    return user


@router.get("/")
async def root() -> dict:
    return ok("online judge api", {
        "service": "python-oj",
        "docs": "/docs",
        "steps": ["problems", "submissions", "users", "logs", "ai"],
    })


@router.get("/health")
async def health() -> dict:
    return ok("healthy", {"data_dir": str(config.DATA_DIR)})


@router.post("/api/reset/")
async def reset_system(user: dict = Depends(_require_admin_or_test_mode)) -> dict:
    """清空测试数据、退出登录状态并重建初始管理员。"""
    from backend.ai import task_manager

    await task_manager.cancel_all()
    await submission_service.clear_all()
    await problem_service.clear_all()
    await log_service.clear_all()
    await language_service.clear_languages()
    await user_service.clear_users()
    await storage.sessions_store.write({"sessions": {}})
    await storage.ai_config_store.write({"config": None})

    await language_service.ensure_builtin_languages()
    await user_service.ensure_initial_admin()
    return ok("system reset successfully", None)
