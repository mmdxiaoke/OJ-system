"""题目数据模型与字段校验（Step 1）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from backend import config
from backend.core.responses import ApiError
from backend.core.storage import ID_PATTERN

MAX_TEXT_LEN = 200_000
MAX_CASES = 200


class CaseItem(BaseModel):
    """样例 / 测试点：input 与 output 两个字段都必须存在。"""

    model_config = ConfigDict(extra="ignore")
    input: str
    output: str


class ProblemPayload(BaseModel):
    """新增/编辑题目的请求体。必填字段缺失或类型错误统一返回 400。"""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    description: str
    input_description: str
    output_description: str
    samples: list[CaseItem]
    constraints: str
    testcases: list[CaseItem]

    hint: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    time_limit: float | None = None
    memory_limit: int | None = None
    author: str | None = None
    difficulty: str | None = None
    public_cases: bool | None = None


def _check_text(name: str, value: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ApiError(400, f"field '{name}' must be a string")
    if not allow_empty and not value.strip():
        raise ApiError(400, f"field '{name}' must not be empty")
    if len(value) > MAX_TEXT_LEN:
        raise ApiError(400, f"field '{name}' is too long (max {MAX_TEXT_LEN} characters)")
    return value


def parse_problem_body(raw: Any, *, expected_id: str | None = None) -> dict:
    """校验并规范化题目配置。

    :param expected_id: PUT 时路径中的 problem_id，必须与请求体中的 id 一致。
    """
    if not isinstance(raw, dict):
        raise ApiError(400, "request body must be a JSON object")
    try:
        payload = ProblemPayload(**raw)
    except ValidationError as exc:
        raise ApiError(400, f"invalid problem config: {_first_error(exc)}") from None

    if not ID_PATTERN.match(payload.id):
        raise ApiError(400, "invalid id: only letters, digits, '_' and '-' are allowed, length 1-64")
    if expected_id is not None and payload.id != expected_id:
        raise ApiError(400, "id in request body does not match problem_id in path")

    for name in ("title", "description", "input_description", "output_description", "constraints"):
        _check_text(name, getattr(payload, name), allow_empty=False)

    if len(payload.samples) > MAX_CASES:
        raise ApiError(400, f"too many samples (max {MAX_CASES})")
    if len(payload.testcases) > MAX_CASES:
        raise ApiError(400, f"too many testcases (max {MAX_CASES})")

    time_limit = None if payload.time_limit is None else float(payload.time_limit)
    if time_limit is not None and (not (time_limit > 0) or time_limit > 60):
        raise ApiError(400, "time_limit must be a positive number no greater than 60 (seconds)")
    memory_limit = None if payload.memory_limit is None else int(payload.memory_limit)
    if memory_limit is not None and (memory_limit < 16 or memory_limit > 4096):
        raise ApiError(400, "memory_limit must be between 16 and 4096 (MB)")

    tags = payload.tags or []
    if not all(isinstance(t, str) for t in tags):
        raise ApiError(400, "tags must be a list of strings")

    return {
        "id": payload.id,
        "title": payload.title,
        "description": payload.description,
        "input_description": payload.input_description,
        "output_description": payload.output_description,
        "samples": [{"input": c.input, "output": c.output} for c in payload.samples],
        "constraints": payload.constraints,
        "testcases": [{"input": c.input, "output": c.output} for c in payload.testcases],
        "hint": payload.hint or "",
        "source": payload.source or "",
        "tags": list(tags),
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "author": payload.author or "",
        "difficulty": payload.difficulty or "",
        "public_cases": bool(payload.public_cases) if payload.public_cases is not None else False,
    }


def with_defaults(problem: dict) -> dict:
    """补全缺失字段，保证 GET 详情返回的字段完整（str -> ""，list -> []）。"""
    out = {
        "id": problem.get("id", ""),
        "title": problem.get("title", ""),
        "description": problem.get("description", ""),
        "input_description": problem.get("input_description", ""),
        "output_description": problem.get("output_description", ""),
        "samples": problem.get("samples") or [],
        "constraints": problem.get("constraints", ""),
        "testcases": problem.get("testcases") or [],
        "hint": problem.get("hint", ""),
        "source": problem.get("source", ""),
        "tags": problem.get("tags") or [],
        "time_limit": float(problem.get("time_limit") or config.DEFAULT_TIME_LIMIT),
        "memory_limit": int(problem.get("memory_limit") or config.DEFAULT_MEMORY_LIMIT),
        "author": problem.get("author", ""),
        "difficulty": problem.get("difficulty", ""),
        "public_cases": bool(problem.get("public_cases", False)),
    }
    return out


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(x) for x in err.get("loc", ()))
    return f"{loc}: {err.get('msg', 'invalid value')}"
