"""Step 2 & 3：提交评测、查询评测结果、评测列表、重新评测。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.deps import get_current_user, require_admin
from backend.core.request import query_param, read_json_body
from backend.core.responses import ApiError, ok
from backend.services import language_service, problem_service, submission_service, user_service

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

MAX_CODE_LEN = 128 * 1024


def _str_field(body: dict, name: str, *, allow_empty: bool = False) -> str:
    if name not in body:
        raise ApiError(400, f"field '{name}' is required")
    value = body[name]
    if not isinstance(value, str):
        raise ApiError(400, f"field '{name}' must be a string")
    if not allow_empty and not value.strip():
        raise ApiError(400, f"field '{name}' must not be empty")
    return value


@router.post("/")
async def submit(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """提交代码并异步启动评测。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")

    problem_id = _str_field(body, "problem_id")
    language = _str_field(body, "language")
    code = _str_field(body, "code")
    if len(code) > MAX_CODE_LEN:
        raise ApiError(400, f"code is too long (max {MAX_CODE_LEN} characters)")

    # 状态码优先级：400 -> 429 -> 404
    await submission_service.check_rate_limit(str(user["user_id"]))
    await problem_service.get_problem_or_404(problem_id)
    await language_service.get_language_or_404(language)

    record = await submission_service.create_submission(str(user["user_id"]), problem_id, language, code)
    await submission_service.start_judge(record["submission_id"])
    return ok("success", {"submission_id": record["submission_id"], "status": "pending"})


@router.get("/")
async def list_submissions(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """查询评测列表（支持 user_id / problem_id / status / 分页）。"""
    user_ref = query_param(request, "user_id")
    problem_id = query_param(request, "problem_id")
    status = query_param(request, "status")
    page = query_param(request, "page")
    page_size = query_param(request, "page_size")

    page, page_size = submission_service.parse_pagination(page, page_size)

    resolved_user = None
    if user_ref is not None:
        resolved_user = await user_service.resolve_user_ref(user_ref)
        if resolved_user is None:
            # 用户不存在：查询结果为空（而不是 404），便于前端直接展示空列表
            return ok("success", {"total": 0, "submissions": []})

    total, records = await submission_service.query_submissions(
        current_user=user,
        user_id=resolved_user,
        problem_id=problem_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return ok("success", {
        "total": total,
        "submissions": [submission_service.summary_view(r) for r in records],
    })


@router.get("/{submission_id}")
async def get_submission(submission_id: str, user: dict = Depends(get_current_user)) -> dict:
    """查询单个评测结果（仅本人或管理员）。"""
    record = await submission_service.get_submission(submission_id)
    if record is None:
        raise ApiError(404, "submission not found")
    if user.get("role") != "admin" and str(record.get("user_id")) != str(user["user_id"]):
        raise ApiError(403, "you can only view your own submissions")
    return ok("success", submission_service.owner_view(record))


@router.put("/{submission_id}/rejudge")
async def rejudge(submission_id: str, user: dict = Depends(require_admin)) -> dict:
    """重新评测（仅管理员）。"""
    record = await submission_service.get_submission(submission_id)
    if record is None:
        raise ApiError(404, "submission not found")
    record = await submission_service.rejudge(submission_id)
    return ok("rejudge started", {"submission_id": submission_id, "status": record.get("status", "pending")})
