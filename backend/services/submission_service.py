"""提交与评测任务管理（Step 2 / Step 3）。"""
from __future__ import annotations

import asyncio
import time

from backend import config
from backend.core import storage
from backend.core.responses import ApiError

_id_lock = asyncio.Lock()
_rate_lock = asyncio.Lock()
_rate_buckets: dict[str, list[float]] = {}

# 后台评测任务表，便于在系统重置时统一取消
_judge_tasks: dict[str, asyncio.Task] = {}


def _record_path(submission_id: str):
    return storage.submission_path(submission_id)


async def _read(submission_id: str) -> dict | None:
    data = await asyncio.to_thread(storage.read_json_file, _record_path(submission_id))
    return data if isinstance(data, dict) else None


async def _write(record: dict) -> None:
    await asyncio.to_thread(storage.write_json_file, _record_path(record["submission_id"]), record)


async def next_submission_id() -> str:
    async with _id_lock:
        existing = await asyncio.to_thread(_max_existing_id)
        return str(existing + 1)


def _max_existing_id() -> int:
    biggest = 0
    if config.SUBMISSION_DIR.exists():
        for path in config.SUBMISSION_DIR.glob("*.json"):
            stem = path.stem
            if stem.isdigit():
                biggest = max(biggest, int(stem))
    return biggest


async def check_rate_limit(user_id: str) -> None:
    """1 分钟内最多提交 3 次。"""
    now = time.time()
    async with _rate_lock:
        bucket = [t for t in _rate_buckets.get(str(user_id), []) if now - t < config.SUBMIT_RATE_WINDOW]
        if len(bucket) >= config.SUBMIT_RATE_MAX:
            _rate_buckets[str(user_id)] = bucket
            raise ApiError(429, f"submit too frequently: at most {config.SUBMIT_RATE_MAX} submissions per minute")
        bucket.append(now)
        _rate_buckets[str(user_id)] = bucket


async def reset_rate_limit() -> None:
    async with _rate_lock:
        _rate_buckets.clear()


async def create_submission(user_id: str, problem_id: str, language: str, code: str) -> dict:
    submission_id = await next_submission_id()
    record = {
        "submission_id": submission_id,
        "user_id": str(user_id),
        "problem_id": problem_id,
        "language": language,
        "code": code,
        "status": "pending",
        "score": None,
        "counts": None,
        "compile_info": None,
        "run_info": None,
        "error_info": None,
        "details": None,
        "time": None,
        "memory": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    await _write(record)
    return record


async def get_submission(submission_id: str) -> dict | None:
    return await _read(submission_id)


async def finish_submission(submission_id: str, **fields) -> dict:
    lock = await storage.submission_lock(submission_id)
    async with lock:
        record = await _read(submission_id)
        if record is None:
            return {}
        record.update(fields)
        record["updated_at"] = time.time()
        await _write(record)
        return record


async def start_judge(submission_id: str) -> None:
    """以异步任务方式启动评测，不阻塞请求。"""
    from backend.judge.engine import judge_submission_task

    old = _judge_tasks.get(submission_id)
    if old is not None and not old.done():
        old.cancel()
    task = asyncio.create_task(judge_submission_task(submission_id), name=f"judge-{submission_id}")
    _judge_tasks[submission_id] = task
    task.add_done_callback(lambda t: _judge_tasks.pop(submission_id, None) if t.done() else None)


async def cancel_all_judges() -> None:
    for task in list(_judge_tasks.values()):
        task.cancel()
    if _judge_tasks:
        await asyncio.gather(*_judge_tasks.values(), return_exceptions=True)
    _judge_tasks.clear()


async def rejudge(submission_id: str) -> dict:
    lock = await storage.submission_lock(submission_id)
    async with lock:
        record = await _read(submission_id)
        if record is None:
            raise ApiError(404, "submission not found")
        record.update({
            "status": "pending",
            "score": None,
            "counts": None,
            "compile_info": None,
            "run_info": None,
            "error_info": None,
            "details": None,
            "time": None,
            "memory": None,
            "updated_at": time.time(),
        })
        await _write(record)
    await start_judge(submission_id)
    return record


async def all_submissions() -> list[dict]:
    def scan() -> list[dict]:
        items = []
        if config.SUBMISSION_DIR.exists():
            for path in config.SUBMISSION_DIR.glob("*.json"):
                data = storage.read_json_file(path)
                if isinstance(data, dict):
                    items.append(data)
        items.sort(key=lambda x: int(x.get("submission_id", 0)))
        return items

    return await asyncio.to_thread(scan)


def parse_pagination(page, page_size) -> tuple[int | None, int | None]:
    """按 API 文档解析分页参数（见 core.pagination）。"""
    from backend.core.pagination import parse_pagination as _parse

    return _parse(page, page_size)


def _matches(record: dict, *, user_id, problem_id, status) -> bool:
    if user_id is not None and str(record.get("user_id")) != str(user_id):
        return False
    if problem_id is not None and str(record.get("problem_id")) != str(problem_id):
        return False
    return not (status is not None and str(record.get("status")) != str(status))


async def query_submissions(
    *,
    current_user: dict,
    user_id: str | None,
    problem_id: str | None,
    status: str | None,
    page: int | None,
    page_size: int | None,
) -> tuple[int, list[dict]]:
    if user_id is None and problem_id is None:
        raise ApiError(400, "at least one of user_id and problem_id is required")
    if status is not None and status not in ("pending", "success", "error"):
        raise ApiError(400, "invalid status, expected one of pending/success/error")

    is_admin = current_user.get("role") == "admin"
    effective_user = user_id
    if user_id is None:
        # 未提供 user_id：管理员可看该题全部提交，普通用户仅能看自己的
        if not is_admin:
            effective_user = str(current_user["user_id"])
    else:
        if not is_admin and str(user_id) != str(current_user["user_id"]):
            raise ApiError(403, "you can only view your own submissions")

    records = await all_submissions()
    filtered = [r for r in records if _matches(r, user_id=effective_user, problem_id=problem_id, status=status)]
    total = len(filtered)
    if page is None and page_size is None:
        return total, filtered
    start = (page - 1) * page_size
    return total, filtered[start:start + page_size]


def summary_view(record: dict) -> dict:
    """列表摘要：pending/error 只返回 submission_id 与 status。"""
    base = {
        "submission_id": str(record["submission_id"]),
        "status": record.get("status"),
    }
    if record.get("status") == "success":
        base["score"] = record.get("score")
        base["counts"] = record.get("counts")
    return base


def detail_view(record: dict) -> dict:
    """详情：pending 时只有 submission_id 与 status，其余字段为 null。"""
    view = {
        "submission_id": str(record["submission_id"]),
        "status": record.get("status"),
        "score": record.get("score"),
        "counts": record.get("counts"),
        "compile_info": record.get("compile_info"),
        "run_info": record.get("run_info"),
        "error_info": record.get("error_info"),
    }
    if record.get("status") == "success":
        view["time"] = record.get("time")
        view["memory"] = record.get("memory")
    return view


def owner_view(record: dict) -> dict:
    """在详情基础上附加前端展示需要的元信息（不含测试点细节）。"""
    view = detail_view(record)
    view.update({
        "user_id": str(record.get("user_id", "")),
        "problem_id": record.get("problem_id"),
        "language": record.get("language"),
        "code": record.get("code", ""),
        "submit_time": record.get("created_at"),
    })
    return view


async def clear_all() -> None:
    await cancel_all_judges()

    def remove_all() -> None:
        if config.SUBMISSION_DIR.exists():
            for path in config.SUBMISSION_DIR.glob("*.json"):
                storage.delete_file(path)

    await asyncio.to_thread(remove_all)
    await reset_rate_limit()
