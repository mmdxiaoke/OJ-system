"""AI 命题任务的调度、进度推送、用量统计与中断（R3 / R4）。"""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from backend.ai import config_store
from backend.ai.llm_client import LLMClient, LLMError
from backend.ai.pipeline import STAGES, TaskContext, run_pipeline
from backend.core import storage
from backend.core.responses import ApiError
from backend.services import problem_service

MAX_TASKS_KEPT = 200
TERMINAL_STATUS = ("success", "failed", "cancelled")


@dataclass
class AITask:
    task_id: str
    user_id: str
    requirement: str
    problem_id: str | None = None
    difficulty: str | None = None
    knowledge_points: list[str] = field(default_factory=list)
    case_count: int = 12
    status: str = "pending"
    progress: str = "任务已创建，等待执行"
    stages: list[dict] = field(default_factory=list)
    result: dict | None = None
    error: str = ""
    usage: dict = field(default_factory=lambda: {
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        "cost": 0.0, "currency": "USD", "estimated": False, "calls": 0,
    })
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    cancel_requested: bool = False
    runner: asyncio.Task | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)

    # ------------------------------------------------------------------
    def public_view(self, *, include_result: bool = True) -> dict:
        data = {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "stages": self.stages,
            "requirement": self.requirement,
            "problem_id": self.problem_id,
            "difficulty": self.difficulty,
            "knowledge_points": self.knowledge_points,
            "case_count": self.case_count,
            "usage": self.usage,
            "error": self.error,
            "created_at": self.created_at,
            "created_time": datetime.fromtimestamp(self.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": self.finished_at,
            "result": self.result if include_result else None,
        }
        return data

    def to_record(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "requirement": self.requirement,
            "problem_id": self.problem_id,
            "difficulty": self.difficulty,
            "knowledge_points": self.knowledge_points,
            "case_count": self.case_count,
            "status": self.status,
            "progress": self.progress,
            "stages": self.stages,
            "result": self.result,
            "error": self.error,
            "usage": self.usage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_tasks: dict[str, AITask] = {}
_lock = asyncio.Lock()
#: 持有后台落盘任务的引用，避免被垃圾回收
_persist_tasks: set[asyncio.Task] = set()


def _stage_title(stage: str) -> str:
    for name, title in STAGES:
        if name == stage:
            return title
    return stage


async def create_task(
    *,
    user: dict,
    requirement: str,
    problem_id: str | None = None,
    difficulty: str | None = None,
    knowledge_points: list[str] | None = None,
    case_count: int = 12,
) -> AITask:
    if not isinstance(requirement, str) or not requirement.strip():
        raise ApiError(400, "field 'requirement' is required")
    if len(requirement) > 4000:
        raise ApiError(400, "requirement is too long (max 4000 characters)")
    if problem_id is not None:
        problem = await problem_service.get_problem(problem_id)
        if problem is None:
            raise ApiError(404, "problem not found")
    try:
        case_count = int(case_count)
    except (TypeError, ValueError):
        raise ApiError(400, "case_count must be an integer") from None
    if not (3 <= case_count <= 30):
        raise ApiError(400, "case_count must be between 3 and 30")

    task = AITask(
        task_id=f"ai-task-{uuid.uuid4().hex[:12]}",
        user_id=str(user["user_id"]),
        requirement=requirement.strip(),
        problem_id=problem_id,
        difficulty=difficulty,
        knowledge_points=[str(k) for k in (knowledge_points or [])][:20],
        case_count=case_count,
    )
    async with _lock:
        _tasks[task.task_id] = task
        _prune()
    task.runner = asyncio.create_task(_run_task(task), name=task.task_id)
    return task


def _prune() -> None:
    if len(_tasks) <= MAX_TASKS_KEPT:
        return
    finished = sorted(
        (t for t in _tasks.values() if t.status in TERMINAL_STATUS),
        key=lambda t: t.created_at,
    )
    for task in finished[: len(_tasks) - MAX_TASKS_KEPT]:
        _tasks.pop(task.task_id, None)


async def _run_task(task: AITask) -> None:
    task.status = "running"
    task.started_at = time.time()
    task.progress = "任务开始执行"
    _publish(task, {"type": "status", "status": task.status, "message": task.progress})

    try:
        model_config = await config_store.resolved_config()
        client = LLMClient(
            provider_url=model_config["provider_url"],
            model=model_config["model"],
            api_key=model_config["api_key"],
        )
        existing = None
        if task.problem_id:
            existing = await problem_service.get_problem(task.problem_id)

        ctx = TaskContext(
            task_id=task.task_id,
            requirement=task.requirement,
            problem_id=task.problem_id,
            difficulty=task.difficulty,
            knowledge_points=task.knowledge_points,
            case_count=task.case_count,
            emit=lambda event: _on_event(task, event),
            add_usage=lambda i, o, u: _add_usage(task, i, o, u, model_config),
            existing_problem=existing,
        )
        task.result = await run_pipeline(ctx, client)
        task.status = "success"
        task.progress = "命题完成，可导入题库"
        task.error = ""
    except asyncio.CancelledError:
        task.status = "cancelled"
        task.progress = "任务已被中断"
        task.finished_at = time.time()
        task.updated_at = task.finished_at
        _publish(task, {"type": "status", "status": task.status, "message": task.progress})
        await _persist(task)
        raise
    except LLMError as exc:
        task.status = "failed"
        task.error = str(exc)
        task.progress = "任务失败"
    except Exception as exc:
        task.status = "failed"
        task.error = f"{exc.__class__.__name__}: {exc}"
        task.progress = "任务失败"
    finally:
        if task.status != "cancelled":
            task.finished_at = time.time()
            task.updated_at = task.finished_at
            _publish(task, {
                "type": "status",
                "status": task.status,
                "message": task.progress,
                "usage": task.usage,
                "error": task.error,
            })
            await _persist(task)


def _on_event(task: AITask, event: dict) -> None:
    etype = event.get("type")
    if etype == "progress":
        message = event.get("message", "")
        task.progress = message
        stage = event.get("stage", "")
        if stage and (not task.stages or task.stages[-1].get("stage") != stage):
            task.stages.append({
                "stage": stage,
                "title": _stage_title(stage),
                "message": message,
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            task.updated_at = time.time()
            handle = asyncio.create_task(_persist(task))
            _persist_tasks.add(handle)
            handle.add_done_callback(_persist_tasks.discard)
    elif etype == "delta":
        # 实时增量文本只推送给前端，不落盘
        pass
    task.updated_at = time.time()
    _publish(task, event)


def _add_usage(task: AITask, input_tokens: int, output_tokens: int, available: bool, model_config: dict) -> None:
    usage = task.usage
    usage["calls"] += 1
    usage["input_tokens"] += max(0, int(input_tokens))
    usage["output_tokens"] += max(0, int(output_tokens))
    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    if not available:
        usage["estimated"] = True
    unit = max(1, int(model_config.get("price_unit") or config_store.DEFAULT_PRICE_UNIT))
    usage["cost"] = round(
        usage["input_tokens"] / unit * float(model_config.get("input_price") or 0.0)
        + usage["output_tokens"] / unit * float(model_config.get("output_price") or 0.0),
        8,
    )
    usage["currency"] = model_config.get("currency", "USD")
    usage["price_unit"] = unit
    usage["input_price"] = float(model_config.get("input_price") or 0.0)
    usage["output_price"] = float(model_config.get("output_price") or 0.0)


# ----------------------------------------------------------------------
# 订阅（SSE）
# ----------------------------------------------------------------------
def _publish(task: AITask, event: dict) -> None:
    payload = {"task_id": task.task_id, **event}
    for queue in list(task.subscribers):
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(payload)


def subscribe(task: AITask) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    task.subscribers.add(queue)
    return queue


def unsubscribe(task: AITask, queue: asyncio.Queue) -> None:
    task.subscribers.discard(queue)


# ----------------------------------------------------------------------
# 查询与中断
# ----------------------------------------------------------------------
async def get_task(task_id: str) -> AITask:
    task = _tasks.get(task_id)
    if task is None:
        task = await _load_task(task_id)
    if task is None:
        raise ApiError(404, "task not found")
    return task


def check_owner(task: AITask, user: dict) -> None:
    if user.get("role") == "admin" or str(task.user_id) == str(user["user_id"]):
        return
    raise ApiError(403, "you have no permission to access this task")


async def list_tasks(user: dict, limit: int = 50) -> list[dict]:
    tasks = sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)
    if user.get("role") != "admin":
        tasks = [t for t in tasks if str(t.user_id) == str(user["user_id"])]
    return [t.public_view(include_result=False) for t in tasks[:limit]]


async def cancel_task(task_id: str, user: dict) -> AITask:
    task = await get_task(task_id)
    check_owner(task, user)
    if task.status in TERMINAL_STATUS:
        raise ApiError(409, "task already finished")
    task.cancel_requested = True
    if task.runner is not None and not task.runner.done():
        task.runner.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task.runner), timeout=10)
    task.status = "cancelled"
    task.progress = "任务已被中断"
    task.finished_at = task.finished_at or time.time()
    task.updated_at = time.time()
    _publish(task, {"type": "status", "status": task.status, "message": task.progress})
    await _persist(task)
    return task


async def cancel_all() -> None:
    for task in list(_tasks.values()):
        if task.status not in TERMINAL_STATUS and task.runner is not None:
            task.runner.cancel()
    runners = [t.runner for t in _tasks.values() if t.runner is not None and not t.runner.done()]
    if runners:
        await asyncio.gather(*runners, return_exceptions=True)
    _tasks.clear()


# ----------------------------------------------------------------------
# 持久化（进程重启后仍能查询历史任务）
# ----------------------------------------------------------------------
async def _persist(task: AITask) -> None:
    record = task.to_record()

    def mutate(data: dict) -> dict:
        tasks = data.setdefault("tasks", {})
        tasks[task.task_id] = record
        return data

    await storage.ai_task_index_store.update(mutate)


async def _load_task(task_id: str) -> AITask | None:
    data = await storage.ai_task_index_store.read()
    record = data.get("tasks", {}).get(task_id)
    if not record:
        return None
    task = AITask(
        task_id=record["task_id"],
        user_id=record.get("user_id", ""),
        requirement=record.get("requirement", ""),
        problem_id=record.get("problem_id"),
        difficulty=record.get("difficulty"),
        knowledge_points=record.get("knowledge_points") or [],
        case_count=record.get("case_count", 12),
    )
    task.status = record.get("status", "failed")
    if task.status == "running":
        task.status = "failed"
        task.error = "服务重启，任务已中断"
    task.progress = record.get("progress", "")
    task.stages = record.get("stages") or []
    task.result = record.get("result")
    task.error = record.get("error", task.error)
    task.usage = record.get("usage") or task.usage
    task.created_at = record.get("created_at", time.time())
    task.updated_at = record.get("updated_at", task.created_at)
    task.started_at = record.get("started_at")
    task.finished_at = record.get("finished_at")
    _tasks[task.task_id] = task
    return task


async def clear_all() -> None:
    await cancel_all()
    await storage.ai_task_index_store.write({"tasks": {}})
