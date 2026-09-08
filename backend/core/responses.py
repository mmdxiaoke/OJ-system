"""统一响应结构与异常体系。

API 文档要求：
* 所有 JSON 响应都必须包含 ``code`` 字段，且与 HTTP 状态码一致；
* 错误响应形如 ``{"code": 404, "msg": "problem not found", "data": null}``；
* 异常优先级：401 > 403 > 400 > 429 > 409 > 404 > 500。
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# 异常优先级表，数值越小优先级越高
STATUS_PRIORITY = {401: 0, 403: 1, 400: 2, 429: 3, 409: 4, 404: 5, 500: 6}

DEFAULT_MESSAGES = {
    200: "success",
    400: "bad request",
    401: "unauthorized",
    403: "forbidden",
    404: "not found",
    409: "conflict",
    429: "too many requests",
    500: "internal server error",
}


class ApiError(Exception):
    """业务异常，会被转换成统一的 JSON 响应。"""

    def __init__(self, status_code: int, msg: str | None = None, data: Any = None) -> None:
        self.status_code = status_code
        self.msg = msg or DEFAULT_MESSAGES.get(status_code, "error")
        self.data = data
        super().__init__(self.msg)

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={"code": self.status_code, "msg": self.msg, "data": self.data},
        )


def ok(msg: str = "success", data: Any = None) -> dict:
    """构造成功响应体（HTTP 200）。"""
    return {"code": 200, "msg": msg, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI 默认返回 422，按 FAQ 要求统一改成 400
        return JSONResponse(
            status_code=400,
            content={
                "code": 400,
                "msg": "request validation error",
                "data": {"errors": _serializable_errors(exc.errors())},
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        if status not in DEFAULT_MESSAGES:
            status = 400 if status < 500 else 500
        detail = exc.detail if isinstance(exc.detail, str) else DEFAULT_MESSAGES[status]
        return JSONResponse(
            status_code=status,
            content={"code": status, "msg": detail, "data": None},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # 不泄露内部堆栈与路径
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": "internal server error", "data": None},
        )


def _serializable_errors(errors: list) -> list:
    out = []
    for err in errors:
        item = {k: v for k, v in err.items() if k != "ctx"}
        loc = item.get("loc")
        if isinstance(loc, tuple):
            item["loc"] = [str(x) for x in loc]
        item.setdefault("msg", "invalid value")
        out.append(item)
    return out
