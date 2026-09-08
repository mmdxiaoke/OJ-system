"""Advance：AI 智能命题接口（R1~R4）。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.ai import config_store, task_manager
from backend.core.deps import get_current_user
from backend.core.request import read_json_body
from backend.core.responses import ApiError, ok
from backend.services import problem_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

TERMINAL = ("success", "failed", "cancelled")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/model-config")
async def get_model_config(user: dict = Depends(get_current_user)) -> dict:
    """读取当前模型配置（不返回密钥明文）。"""
    return ok("success", await config_store.public_config())


@router.put("/model-config")
async def update_model_config(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """配置提供商 URL / 模型名称 / 模型密钥与计价方式。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    config = await config_store.save_config(body)
    return ok("model config updated", config)


@router.post("/problem-tasks/")
async def create_task(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """创建智能命题任务（后台异步执行）。"""
    body = await read_json_body(request)
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    task = await task_manager.create_task(
        user=user,
        requirement=body.get("requirement"),
        problem_id=body.get("problem_id"),
        difficulty=body.get("difficulty"),
        knowledge_points=body.get("knowledge_points"),
        case_count=body.get("case_count", 12),
    )
    return ok("task created", {"task_id": task.task_id, "status": task.status})


@router.get("/problem-tasks/")
async def list_tasks(user: dict = Depends(get_current_user)) -> dict:
    """查询当前用户可见的命题任务列表。"""
    return ok("success", await task_manager.list_tasks(user))


@router.get("/problem-tasks/{task_id}")
async def get_task(task_id: str, user: dict = Depends(get_current_user)) -> dict:
    """查询任务状态、进度、结果与 Token 用量。"""
    task = await task_manager.get_task(task_id)
    task_manager.check_owner(task, user)
    return ok("success", task.public_view())


@router.get("/problem-tasks/{task_id}/events")
async def task_events(task_id: str, request: Request, user: dict = Depends(get_current_user)) -> StreamingResponse:
    """SSE 实时进度流（也支持前端轮询作为替代）。"""
    task = await task_manager.get_task(task_id)
    task_manager.check_owner(task, user)

    async def event_stream():
        queue = task_manager.subscribe(task)
        try:
            yield _sse("snapshot", task.public_view(include_result=False))
            if task.status in TERMINAL:
                yield _sse("status", {
                    "task_id": task.task_id,
                    "status": task.status,
                    "message": task.progress,
                    "usage": task.usage,
                })
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event.get("type", "message"), event)
                if event.get("type") == "status" and event.get("status") in TERMINAL:
                    break
        finally:
            task_manager.unsubscribe(task, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/problem-tasks/{task_id}/cancel")
async def cancel_task(task_id: str, user: dict = Depends(get_current_user)) -> dict:
    """中断正在执行的命题任务（真正取消后台 asyncio 任务与 HTTP 请求）。"""
    task = await task_manager.cancel_task(task_id, user)
    return ok("task cancelled", {"task_id": task.task_id, "status": task.status})


@router.post("/problem-tasks/{task_id}/apply")
async def apply_task(request: Request, task_id: str, user: dict = Depends(get_current_user)) -> dict:
    """把命题结果导入题库（新增或覆盖），衔接 Step 1 的题目管理。"""
    task = await task_manager.get_task(task_id)
    task_manager.check_owner(task, user)
    if task.status != "success" or not task.result:
        raise ApiError(409, "task has not finished successfully")
    body = await read_json_body(request)
    mode = (body or {}).get("mode", "create") if isinstance(body, dict) else "create"
    if mode not in ("create", "update"):
        raise ApiError(400, "mode must be 'create' or 'update'")

    from backend.models.problem import parse_problem_body

    problem = parse_problem_body(task.result.get("problem") or {})
    exists = await problem_service.exists(problem["id"])
    if mode == "create":
        if exists:
            raise ApiError(409, "problem id already exists, use update mode instead")
        await problem_service.create_problem(problem)
        return ok("problem created from ai task", {"id": problem["id"]})
    if not exists:
        raise ApiError(404, "problem not found, use create mode instead")
    await problem_service.update_problem(problem)
    return ok("problem updated from ai task", {"id": problem["id"]})
