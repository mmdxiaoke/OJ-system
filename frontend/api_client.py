"""统一的后端 API 客户端。

所有页面都必须通过这里调用 REST API，不直接读写后端数据文件。
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_BASE = os.environ.get("OJ_API_BASE", "http://127.0.0.1:8000")
TIMEOUT = float(os.environ.get("OJ_API_TIMEOUT", "30"))


@dataclass
class ApiResult:
    """统一的响应封装：同时保留 HTTP 状态码与响应体。"""

    status: int
    code: int
    msg: str
    data: Any = None
    network_error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.code == 200

    def __bool__(self) -> bool:  # 方便 `if result:`
        return self.ok

    def error_text(self) -> str:
        if self.network_error:
            return f"无法连接后端：{self.network_error}"
        return f"HTTP {self.status} | code={self.code} | {self.msg}"


class OJClient:
    """基于 requests.Session 的客户端，Cookie 中的会话自动保持。"""

    def __init__(self, base_url: str = DEFAULT_BASE) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.current_user: dict | None = None

    # ------------------------------------------------------------------
    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def request(self, method: str, path: str, **kwargs) -> ApiResult:
        kwargs.setdefault("timeout", TIMEOUT)
        try:
            resp = self.session.request(method.upper(), self._url(path), **kwargs)
        except requests.RequestException as exc:
            return ApiResult(0, 0, "network error", None, network_error=str(exc))
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"code": resp.status_code, "msg": "invalid response", "data": payload}
        return ApiResult(
            status=resp.status_code,
            code=int(payload.get("code", resp.status_code) or 0),
            msg=str(payload.get("msg", "")),
            data=payload.get("data"),
        )

    def get(self, path: str, **params) -> ApiResult:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, json_body: dict | None = None) -> ApiResult:
        return self.request("POST", path, json=json_body if json_body is not None else {})

    def put(self, path: str, json_body: dict | None = None) -> ApiResult:
        return self.request("PUT", path, json=json_body if json_body is not None else {})

    def delete(self, path: str) -> ApiResult:
        return self.request("DELETE", path)

    # ------------------------------------------------------------------
    # 用户
    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> ApiResult:
        result = self.post("/api/auth/login", {"username": username, "password": password})
        if result.ok and isinstance(result.data, dict):
            self.current_user = result.data
        return result

    def logout(self) -> ApiResult:
        result = self.post("/api/auth/logout", {})
        self.current_user = None
        return result

    def register(self, username: str, password: str) -> ApiResult:
        return self.post("/api/users/", {"username": username, "password": password})

    def me(self, user_id: str) -> ApiResult:
        return self.get(f"/api/users/{user_id}")

    def list_users(self, page: int | None = None, page_size: int | None = None) -> ApiResult:
        return self.get("/api/users/", page=page, page_size=page_size)

    def set_role(self, user_id: str, role: str) -> ApiResult:
        return self.put(f"/api/users/{user_id}/role", {"role": role})

    def create_admin(self, username: str, password: str) -> ApiResult:
        return self.post("/api/users/admin", {"username": username, "password": password})

    # ------------------------------------------------------------------
    # 题目
    # ------------------------------------------------------------------
    def list_problems(self) -> ApiResult:
        return self.get("/api/problems/")

    def get_problem(self, problem_id: str) -> ApiResult:
        return self.get(f"/api/problems/{problem_id}")

    def create_problem(self, problem: dict) -> ApiResult:
        return self.post("/api/problems/", problem)

    def update_problem(self, problem_id: str, problem: dict) -> ApiResult:
        return self.put(f"/api/problems/{problem_id}", problem)

    def delete_problem(self, problem_id: str) -> ApiResult:
        return self.delete(f"/api/problems/{problem_id}")

    def set_log_visibility(self, problem_id: str, public_cases: bool) -> ApiResult:
        return self.put(f"/api/problems/{problem_id}/log_visibility", {"public_cases": public_cases})

    # ------------------------------------------------------------------
    # 语言与评测
    # ------------------------------------------------------------------
    def list_languages(self) -> ApiResult:
        return self.get("/api/languages/")

    def register_language(self, config: dict) -> ApiResult:
        return self.post("/api/languages/", config)

    def submit(self, problem_id: str, language: str, code: str) -> ApiResult:
        return self.post("/api/submissions/", {
            "problem_id": problem_id, "language": language, "code": code,
        })

    def list_submissions(self, **filters) -> ApiResult:
        return self.get("/api/submissions/", **filters)

    def get_submission(self, submission_id: str) -> ApiResult:
        return self.get(f"/api/submissions/{submission_id}")

    def rejudge(self, submission_id: str) -> ApiResult:
        return self.put(f"/api/submissions/{submission_id}/rejudge", {})

    def get_log(self, submission_id: str) -> ApiResult:
        return self.get(f"/api/submissions/{submission_id}/log")

    def access_logs(self, **filters) -> ApiResult:
        return self.get("/api/logs/access/", **filters)

    # ------------------------------------------------------------------
    # AI 智能命题
    # ------------------------------------------------------------------
    def get_model_config(self) -> ApiResult:
        return self.get("/api/ai/model-config")

    def set_model_config(self, config: dict) -> ApiResult:
        return self.put("/api/ai/model-config", config)

    def create_ai_task(self, payload: dict) -> ApiResult:
        return self.post("/api/ai/problem-tasks/", payload)

    def list_ai_tasks(self) -> ApiResult:
        return self.get("/api/ai/problem-tasks/")

    def get_ai_task(self, task_id: str) -> ApiResult:
        return self.get(f"/api/ai/problem-tasks/{task_id}")

    def cancel_ai_task(self, task_id: str) -> ApiResult:
        return self.put(f"/api/ai/problem-tasks/{task_id}/cancel", {})

    def apply_ai_task(self, task_id: str, mode: str) -> ApiResult:
        return self.post(f"/api/ai/problem-tasks/{task_id}/apply", {"mode": mode})

    def ai_events(self, task_id: str) -> Iterator[tuple[str, dict]]:
        """以 SSE 方式读取任务实时进度，逐条 yield (event, data)。"""
        url = self._url(f"/api/ai/problem-tasks/{task_id}/events")
        try:
            with self.session.get(url, stream=True, timeout=(10, 300)) as resp:
                if resp.status_code != 200:
                    yield "error", {"status": resp.status_code, "message": "无法建立进度连接"}
                    return
                event_name = "message"
                for raw in resp.iter_lines(decode_unicode=True):
                    if raw is None:
                        continue
                    line = raw.strip()
                    if not line:
                        continue
                    if line.startswith(":"):
                        yield "heartbeat", {}
                        continue
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        yield event_name, data
                        if event_name == "status" and data.get("status") in ("success", "failed", "cancelled"):
                            return
        except requests.RequestException as exc:
            yield "error", {"message": f"进度连接中断：{exc}"}
