"""Step 5：评测日志可见性与访问审计。"""
from __future__ import annotations

from datetime import datetime

from backend.core import storage
from backend.core.pagination import paginate, parse_pagination

MAX_ACCESS_LOGS = 20_000


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def record_access(user_id: str, problem_id: str, status: int, action: str = "view_logs") -> None:
    """记录一次日志访问。

    只记录「已登录且 submission 存在」的访问（由调用方保证），
    未登录 / 提交不存在 / 参数错误不记录。
    """
    entry = {
        "user_id": str(user_id),
        "problem_id": str(problem_id),
        "action": action,
        "time": _now_date(),
        "timestamp": _now_full(),
        "status": str(status),
    }

    def mutate(data: dict) -> dict:
        logs = data.setdefault("logs", [])
        logs.append(entry)
        if len(logs) > MAX_ACCESS_LOGS:
            del logs[: len(logs) - MAX_ACCESS_LOGS]
        return data

    await storage.access_log_store.update(mutate)


async def query_access_logs(
    *,
    user_id: str | None,
    problem_id: str | None,
    page: str | None,
    page_size: str | None,
) -> list[dict]:
    page, page_size = parse_pagination(page, page_size)
    data = await storage.access_log_store.read()
    logs = data.get("logs", [])
    if user_id is not None:
        logs = [x for x in logs if str(x.get("user_id")) == str(user_id)]
    if problem_id is not None:
        logs = [x for x in logs if str(x.get("problem_id")) == str(problem_id)]
    logs = list(reversed(logs))
    return paginate(logs, page, page_size)


async def clear_all() -> None:
    await storage.access_log_store.write({"logs": []})
