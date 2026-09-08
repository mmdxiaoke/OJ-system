"""Step 5：评测日志、可见性配置与访问审计接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.deps import get_current_user, require_admin
from backend.core.request import query_param, read_json_body_optional
from backend.core.responses import ApiError, ok
from backend.core.storage import ID_PATTERN
from backend.services import log_service, problem_service, submission_service, user_service

router = APIRouter(tags=["logs"])


@router.get("/api/submissions/{submission_id}/log")
async def get_submission_log(submission_id: str, user: dict = Depends(get_current_user)) -> dict:
    """查询评测日志（测例明细）。

    可见性规则：
    * 管理员：始终可见 details；
    * 提交者本人：仅当题目 ``public_cases`` 为 True 时可见 details；
    * 其他登录用户：题目 ``public_cases`` 为 True 时可查看该评测的日志，否则 403。
    """
    record = await submission_service.get_submission(submission_id)
    if record is None:
        raise ApiError(404, "submission not found")

    is_admin = user.get("role") == "admin"
    is_owner = str(record.get("user_id")) == str(user["user_id"])
    problem_id = str(record.get("problem_id", ""))
    problem = await problem_service.get_problem(problem_id) if ID_PATTERN.match(problem_id or "") else None
    public_cases = bool(problem.get("public_cases")) if problem else False

    allowed = is_admin or is_owner or public_cases
    await log_service.record_access(str(user["user_id"]), problem_id, 200 if allowed else 403)
    if not allowed:
        raise ApiError(403, "you have no permission to view this log")

    show_details = is_admin or public_cases
    details = record.get("details") if show_details else None
    data = {
        "score": record.get("score"),
        "counts": record.get("counts"),
    }
    if show_details:
        data["details"] = details or []
    return ok("success", data)


@router.put("/api/problems/{problem_id}/log_visibility")
async def set_log_visibility(problem_id: str, request: Request, user: dict = Depends(require_admin)) -> dict:
    """配置题目评测日志的可见性（仅管理员）。"""
    body = await read_json_body_optional(request)
    public_cases = body.get("public_cases", False)
    if not isinstance(public_cases, bool):
        raise ApiError(400, "field 'public_cases' must be a boolean")
    data = await problem_service.set_log_visibility(problem_id, public_cases)
    return ok("log visibility updated", data)


@router.get("/api/logs/access/")
async def list_access_logs(request: Request, user: dict = Depends(require_admin)) -> dict:
    """日志访问审计（仅管理员）。"""
    user_ref = query_param(request, "user_id")
    problem_id = query_param(request, "problem_id")
    page = query_param(request, "page")
    page_size = query_param(request, "page_size")

    resolved = None
    if user_ref is not None:
        resolved = await user_service.resolve_user_ref(user_ref)
        if resolved is None:
            return ok("success", [])

    logs = await log_service.query_access_logs(
        user_id=resolved, problem_id=problem_id, page=page, page_size=page_size
    )
    return ok("success", logs)
