"""请求体读取工具。"""
from __future__ import annotations

from typing import Any

from fastapi import Request

from backend.core.responses import ApiError


async def read_json_body(request: Request) -> Any:
    """读取 JSON 请求体，解析失败统一返回 400。"""
    raw = await request.body()
    if not raw:
        raise ApiError(400, "request body is required")
    try:
        return await request.json()
    except Exception:
        raise ApiError(400, "request body must be valid JSON") from None


async def read_json_body_optional(request: Request) -> dict:
    """读取 JSON 请求体，允许空请求体（返回空 dict）。"""
    raw = await request.body()
    if not raw:
        return {}
    try:
        body = await request.json()
    except Exception:
        raise ApiError(400, "request body must be valid JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    return body


def query_param(request: Request, name: str) -> str | None:
    """取出查询参数；空字符串按未提供处理。"""
    value = request.query_params.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None
