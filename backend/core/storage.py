"""基于 JSON 文件的持久化层。

设计取舍：本实验规模较小（数千条记录），用「JSON 文件 + 进程内异步锁」即可
满足需求，且便于助教直接查看数据。所有写操作都是「先写临时文件再原子替换」，
避免进程中断产生半个文件。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend import config

# 题目 id / 提交 id 的合法字符，防止路径穿越
ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def validate_id(value: str, field: str = "id") -> str:
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        from backend.core.responses import ApiError

        raise ApiError(400, f"invalid {field}: only letters, digits, '_' and '-' are allowed, length 1-64")
    return value


def ensure_dirs() -> None:
    for d in config.DATA_DIRS:
        d.mkdir(parents=True, exist_ok=True)


class JsonFile:
    """单个 JSON 文件的读写封装（带异步锁）。"""

    def __init__(self, path: Path, default: Any) -> None:
        self.path = path
        self._default = default
        self._lock = asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    def read_sync(self) -> Any:
        if not self.path.exists():
            return json.loads(json.dumps(self._default))
        try:
            with self.path.open("r", encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(self._default))

    async def read(self) -> Any:
        async with self._lock:
            return await asyncio.to_thread(self.read_sync)

    async def write(self, data: Any) -> None:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, data)

    def _write_sync(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                with contextlib.suppress(OSError):
                    os.remove(tmp)

    async def update(self, mutator: Callable[[Any], Any]) -> Any:
        """在锁内执行「读-改-写」，mutator 返回值即写入内容（None 表示不写）。"""
        async with self._lock:
            data = await asyncio.to_thread(self.read_sync)
            new_data = mutator(data)
            if new_data is not None:
                await asyncio.to_thread(self._write_sync, new_data)
                return new_data
            return data


# ---------------------------------------------------------------------------
# 各类数据文件
# ---------------------------------------------------------------------------
users_store = JsonFile(config.USERS_FILE, {"next_id": 1, "users": {}})
sessions_store = JsonFile(config.SESSIONS_FILE, {"sessions": {}})
languages_store = JsonFile(config.LANGUAGES_FILE, {"languages": {}})
access_log_store = JsonFile(config.ACCESS_LOG_FILE, {"logs": []})
ai_config_store = JsonFile(config.AI_CONFIG_FILE, {"config": None})
ai_task_index_store = JsonFile(config.AI_TASKS_INDEX_FILE, {"next_id": 1, "tasks": {}})


def problem_path(problem_id: str) -> Path:
    return config.PROBLEM_DIR / f"{problem_id}.json"


def submission_path(submission_id: str) -> Path:
    return config.SUBMISSION_DIR / f"{submission_id}.json"


def ai_task_path(task_id: str) -> Path:
    return config.AI_TASK_DIR / f"{task_id}.json"


def read_json_file(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except (json.JSONDecodeError, OSError):
        return None


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            with contextlib.suppress(OSError):
                os.remove(tmp)


def delete_file(path: Path) -> bool:
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


# 每个题目/提交一个文件，用独立锁保护
_problem_locks: dict[str, asyncio.Lock] = {}
_submission_locks: dict[str, asyncio.Lock] = {}
_lock_guard = asyncio.Lock()


async def _get_lock(table: dict[str, asyncio.Lock], key: str) -> asyncio.Lock:
    lock = table.get(key)
    if lock is None:
        async with _lock_guard:
            lock = table.setdefault(key, asyncio.Lock())
    return lock


def problem_lock(problem_id: str) -> Any:
    return _get_lock(_problem_locks, problem_id)


def submission_lock(submission_id: str) -> Any:
    return _get_lock(_submission_locks, submission_id)
