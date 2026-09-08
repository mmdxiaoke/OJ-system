"""用户提交统计：submit_count（按提交算）与 resolve_count（按题目算）。"""
from __future__ import annotations

from backend.services import submission_service


def _is_accepted(record: dict) -> bool:
    counts = record.get("counts") or 0
    score = record.get("score")
    return (
        record.get("status") == "success"
        and isinstance(score, int)
        and counts > 0
        and score >= counts
    )


def summarize(records: list[dict]) -> dict[str, dict]:
    """一次扫描得出所有用户的统计信息。"""
    stats: dict[str, dict] = {}
    resolved: dict[str, set] = {}
    for record in records:
        uid = str(record.get("user_id", ""))
        if not uid:
            continue
        entry = stats.setdefault(uid, {"submit_count": 0, "resolve_count": 0})
        entry["submit_count"] += 1
        if _is_accepted(record):
            resolved.setdefault(uid, set()).add(str(record.get("problem_id")))
    for uid, problems in resolved.items():
        stats[uid]["resolve_count"] = len(problems)
    return stats


async def all_user_stats() -> dict[str, dict]:
    records = await submission_service.all_submissions()
    return summarize(records)


async def user_stats(user_id: str) -> dict:
    stats = await all_user_stats()
    return stats.get(str(user_id), {"submit_count": 0, "resolve_count": 0})
