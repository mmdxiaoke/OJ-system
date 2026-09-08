"""题目服务：配置文件的读写与查询。"""
from __future__ import annotations

import asyncio

from backend import config
from backend.core import storage
from backend.core.responses import ApiError
from backend.models.problem import with_defaults


async def list_problems() -> list[dict]:
    """返回所有题目的简要信息。"""

    def scan() -> list[dict]:
        items = []
        if config.PROBLEM_DIR.exists():
            for path in sorted(config.PROBLEM_DIR.glob("*.json")):
                data = storage.read_json_file(path)
                if isinstance(data, dict) and data.get("id"):
                    items.append({"id": data["id"], "title": data.get("title", "")})
        items.sort(key=lambda x: x["id"])
        return items

    return await asyncio.to_thread(scan)


async def get_problem(problem_id: str) -> dict | None:
    data = await asyncio.to_thread(storage.read_json_file, storage.problem_path(problem_id))
    if not isinstance(data, dict):
        return None
    return with_defaults(data)


async def get_problem_raw(problem_id: str) -> dict | None:
    """返回磁盘上的原始配置（未补默认值），供评测确定生效的资源限制。"""
    data = await asyncio.to_thread(storage.read_json_file, storage.problem_path(problem_id))
    return data if isinstance(data, dict) else None


async def get_problem_or_404(problem_id: str) -> dict:
    problem = await get_problem(problem_id)
    if problem is None:
        raise ApiError(404, "problem not found")
    return problem


async def exists(problem_id: str) -> bool:
    return await asyncio.to_thread(storage.problem_path(problem_id).exists)


async def save_problem(problem: dict) -> None:
    lock = await storage.problem_lock(problem["id"])
    async with lock:
        await asyncio.to_thread(storage.write_json_file, storage.problem_path(problem["id"]), problem)


async def create_problem(problem: dict) -> None:
    lock = await storage.problem_lock(problem["id"])
    async with lock:
        path = storage.problem_path(problem["id"])
        if await asyncio.to_thread(path.exists):
            raise ApiError(409, "problem id already exists")
        await asyncio.to_thread(storage.write_json_file, path, problem)


async def update_problem(problem: dict) -> None:
    lock = await storage.problem_lock(problem["id"])
    async with lock:
        path = storage.problem_path(problem["id"])
        if not await asyncio.to_thread(path.exists):
            raise ApiError(404, "problem not found")
        await asyncio.to_thread(storage.write_json_file, path, problem)


async def delete_problem(problem_id: str) -> None:
    lock = await storage.problem_lock(problem_id)
    async with lock:
        path = storage.problem_path(problem_id)
        if not await asyncio.to_thread(storage.delete_file, path):
            raise ApiError(404, "problem not found")


async def set_log_visibility(problem_id: str, public_cases: bool) -> dict:
    lock = await storage.problem_lock(problem_id)
    async with lock:
        path = storage.problem_path(problem_id)
        data = await asyncio.to_thread(storage.read_json_file, path)
        if not isinstance(data, dict):
            raise ApiError(404, "problem not found")
        data["public_cases"] = bool(public_cases)
        await asyncio.to_thread(storage.write_json_file, path, data)
        return {"problem_id": problem_id, "public_cases": bool(public_cases)}


async def clear_all() -> None:
    def remove_all() -> None:
        if config.PROBLEM_DIR.exists():
            for path in config.PROBLEM_DIR.glob("*.json"):
                storage.delete_file(path)

    await asyncio.to_thread(remove_all)
