"""FastAPI 应用工厂。"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from backend.core.responses import register_exception_handlers
from backend.core.security import ensure_storage
from backend.core.storage import ensure_dirs
from backend.routers import (
    ai,
    auth,
    languages,
    logs,
    problems,
    submissions,
    system,
    users,
)
from backend.services import language_service, user_service

logger = logging.getLogger("oj")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DESCRIPTION = """
程序设计训练（Python）大作业：小型 Online Judge 系统。

* 全部接口使用 FastAPI 异步接口（`async def`）实现；
* 统一响应结构 `{code, msg, data}`，`code` 与 HTTP 状态码一致；
* 权限判断全部在后端完成。
"""


def create_app() -> FastAPI:
    ensure_dirs()
    app = FastAPI(
        title="Python OJ",
        description=DESCRIPTION,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        # 只记录方法、路径、状态码和耗时，绝不记录请求体（可能含密码 / 密钥 / 代码）
        logger.info(
            "%s %s -> %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(problems.router)
    app.include_router(languages.router)
    app.include_router(submissions.router)
    app.include_router(logs.router)
    app.include_router(ai.router)

    @app.on_event("startup")
    async def _startup() -> None:
        ensure_storage()
        await language_service.ensure_builtin_languages()
        admin = await user_service.ensure_initial_admin()
        logger.info("system ready, data dir = %s, admin id = %s", config.DATA_DIR, admin.get("user_id"))

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        from backend.services import submission_service

        await submission_service.cancel_all_judges()

    return app


app = create_app()
