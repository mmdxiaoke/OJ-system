"""Step 1：题目管理接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.deps import get_current_user, require_admin
from backend.core.request import read_json_body
from backend.core.responses import ApiError, ok
from backend.core.storage import ID_PATTERN
from backend.models.problem import parse_problem_body
from backend.services import problem_service

router = APIRouter(prefix="/api/problems", tags=["problems"])


def _check_id(problem_id: str) -> str:
    if not ID_PATTERN.match(problem_id or ""):
        raise ApiError(404, "problem not found")
    return problem_id


@router.get("/")
async def list_problems(user: dict = Depends(get_current_user)) -> dict:
    """查看题目列表（所有已登录用户）。"""
    problems = await problem_service.list_problems()
    return ok("success", problems)


@router.post("/")
async def add_problem(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """添加题目。"""
    body = await read_json_body(request)
    problem = parse_problem_body(body)
    await problem_service.create_problem(problem)
    return ok("add success", {"id": problem["id"]})


@router.get("/{problem_id}")
async def get_problem(problem_id: str, user: dict = Depends(get_current_user)) -> dict:
    """查看题目详情。"""
    problem = await problem_service.get_problem(_check_id(problem_id))
    if problem is None:
        raise ApiError(404, "problem not found")
    return ok("success", problem)


@router.put("/{problem_id}")
async def update_problem(problem_id: str, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """编辑题目（覆盖原配置）。"""
    _check_id(problem_id)
    body = await read_json_body(request)
    problem = parse_problem_body(body, expected_id=problem_id)
    await problem_service.update_problem(problem)
    return ok("update success", {"id": problem["id"]})


@router.delete("/{problem_id}")
async def delete_problem(problem_id: str, user: dict = Depends(require_admin)) -> dict:
    """删除题目（仅管理员）。"""
    _check_id(problem_id)
    await problem_service.delete_problem(problem_id)
    return ok("delete success", {"id": problem_id})
