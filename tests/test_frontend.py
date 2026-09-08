"""前端测试：用 Streamlit 官方 AppTest 真正执行页面脚本。

覆盖两类内容：
1. **页面渲染冒烟**：每个页面组都能正常渲染，不抛异常；
2. **交互流程**：登录、用图形表单新建题目、界面提交代码并轮询结果、
   从下拉列表查看提交详情、管理员用下拉框变更用户角色。

用法：
    python -m tests.test_frontend
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP = str(ROOT / "frontend" / "app.py")
PAGES = ["仪表盘", "用户中心", "题库", "评测中心", "AI 智能命题"]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_backend(data_dir: str, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["OJ_DATA_DIR"] = data_dir
    env["OJ_RESET_OPEN"] = "1"
    log = open(Path(data_dir) / "server.log", "w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
    )


def wait_health(base: str, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{base}/health", timeout=3).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.4)
    return False


def _state_user(at) -> dict | None:
    """安全读取 session_state 中的登录用户。"""
    try:
        return at.session_state["user"]
    except (KeyError, AttributeError):
        return None


def state_value(at, key: str, default=None):
    """安全读取 AppTest 的 session_state（它不支持 .get）。"""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def page_text(at) -> str:
    """把页面上所有可见文本拼起来，便于断言。"""
    parts: list[str] = []
    for attr in ("markdown", "metric", "success", "info", "warning", "error", "caption",
                 "code", "json", "dataframe", "text", "header", "subheader", "button",
                 "title", "toast"):
        for element in getattr(at, attr, None) or []:
            for field in ("value", "label", "body", "text"):
                value = getattr(element, field, None)
                if value is not None:
                    parts.append(str(value))
    return " ".join(parts)


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  [PASS] {name}")
            return True
        self.failures.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} -> {detail}")
        return False

    def no_exception(self, at, name: str) -> bool:
        if at.exception:
            return self.check(name, False, str(at.exception[0].value))
        return self.check(name, True)


def main() -> int:
    from streamlit.testing.v1 import AppTest

    data_dir = tempfile.mkdtemp(prefix="oj_front_")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    os.environ["OJ_API_BASE"] = base
    proc = start_backend(data_dir, port)
    checker = Checker()

    try:
        if not wait_health(base):
            print("后端启动失败")
            print((Path(data_dir) / "server.log").read_text(encoding="utf-8", errors="replace"))
            return 2

        api = requests.Session()
        api.post(f"{base}/api/auth/login",
                 json={"username": "admin", "password": "admintestpassword"}, timeout=10)
        # 预置一个题目 + 一个待改角色的用户
        api.post(f"{base}/api/problems/", json={
            "id": "p_front", "title": "前端测试题", "description": "求 a+b",
            "input_description": "两个整数", "output_description": "和",
            "samples": [{"input": "1 2", "output": "3"}], "constraints": "|a|,|b|<=1e9",
            "testcases": [{"input": "1 2\n", "output": "3\n"}],
        }, timeout=10)
        api.post(f"{base}/api/users/", json={"username": "victim01", "password": "password123"}, timeout=10)
        victim_id = str(api.get(f"{base}/api/users/", params={"page": 1, "page_size": 50},
                                timeout=10).json()["data"]["users"][-1]["user_id"])

        print("\n=== 页面渲染 ===")
        at = AppTest.from_file(APP, default_timeout=90)
        at.session_state["api_base"] = base
        at.run()
        checker.no_exception(at, "首页（未登录）渲染无异常")
        checker.check("未登录时显示欢迎引导", "注册" in page_text(at), page_text(at)[:120])

        for page in PAGES:
            at.session_state["api_base"] = base
            at.sidebar.radio[0].set_value(page).run()
            checker.no_exception(at, f"{page} 页面渲染无异常")

        print("\n=== 登录流程 ===")
        at.sidebar.radio[0].set_value("用户中心").run()
        at.text_input(key="login_username").set_value("admin")
        at.text_input(key="login_password").set_value("admintestpassword")
        at.button(key="login_submit").click().run()
        user = _state_user(at)
        checker.check("登录成功并写入会话", user is not None and user.get("username") == "admin", str(user))

        for page in PAGES:
            at.sidebar.radio[0].set_value(page).run()
            checker.no_exception(at, f"登录后 {page} 页面渲染无异常")

        print("\n=== 仪表盘 ===")
        at.sidebar.radio[0].set_value("仪表盘").run()
        dashboard_text = page_text(at)
        checker.check("仪表盘显示题库题目数", "题库题目" in dashboard_text, dashboard_text[:150])
        checker.check("仪表盘显示快捷操作", "快捷操作" in dashboard_text, dashboard_text[:150])

        print("\n=== 用图形表单新建题目 ===")
        at.sidebar.radio[0].set_value("题库").run()
        at.text_input(key="create_id").set_value("p_ui")
        at.text_input(key="create_title").set_value("界面创建的题目")
        at.text_area(key="create_desc").set_value("输入两个整数，输出它们的和。")
        at.text_area(key="create_in_desc").set_value("一行两个整数 a b")
        at.text_area(key="create_out_desc").set_value("一行一个整数 a+b")
        at.text_input(key="create_constraints").set_value("|a|,|b| <= 10^9")
        at.text_area(key="create_sample_0_in").set_value("1 2")
        at.text_area(key="create_sample_0_out").set_value("3")
        at.text_area(key="create_case_0_in").set_value("1 2\n")
        at.text_area(key="create_case_0_out").set_value("3\n")
        at.button(key="create_submit_form").click().run()
        checker.no_exception(at, "表单提交无异常")
        created = api.get(f"{base}/api/problems/p_ui", timeout=10)
        checker.check("表单新建的题目已入库", created.status_code == 200, f"HTTP {created.status_code}")
        if created.status_code == 200:
            body = created.json()["data"]
            checker.check("表单字段写入正确", body.get("title") == "界面创建的题目", str(body.get("title")))
            checker.check("样例与测试点已写入",
                          len(body.get("samples") or []) >= 1 and len(body.get("testcases") or []) >= 1,
                          str(body.get("testcases")))

        print("\n=== 界面提交代码并轮询结果 ===")
        at.sidebar.radio[0].set_value("评测中心").run()
        at.selectbox(key="submit_pick").set_value("p_ui").run()
        at.selectbox(key="sub_lang").set_value("python").run()
        at.button(key="insert_template").click().run()
        checker.check("插入代码模板写入代码框",
                      "def main" in str(state_value(at, "sub_code", "")),
                      str(state_value(at, "sub_code", ""))[:60])
        at.text_area(key="sub_code").set_value("a, b = map(int, input().split())\nprint(a + b)\n")
        at.button(key="submit_btn").click().run()
        checker.no_exception(at, "提交并轮询无异常")
        submission_text = page_text(at)
        checker.check("提交后展示评测结果", "已完成" in submission_text or "AC" in submission_text,
                      submission_text[:200])

        listed = api.get(f"{base}/api/submissions/", params={"problem_id": "p_ui"}, timeout=10).json()
        submissions = listed.get("data", {}).get("submissions", [])
        checker.check("界面提交已入库", len(submissions) == 1, str(listed))
        if submissions:
            detail = api.get(f"{base}/api/submissions/{submissions[0]['submission_id']}", timeout=10).json()
            data = detail.get("data", {})
            checker.check("界面提交评测为满分", data.get("score") == data.get("counts"),
                          str(data.get("score")) + "/" + str(data.get("counts")))

        print("\n=== 从下拉列表查看提交详情 ===")
        at.sidebar.radio[0].set_value("评测中心").run()
        detail_options = [o for o in at.selectbox(key="detail_sid").options]
        checker.check("提交详情下拉自动列出我的提交", len(detail_options) >= 1, str(detail_options))
        if detail_options:
            at.selectbox(key="detail_sid").set_value(detail_options[0]).run()
            detail_text = page_text(at)
            checker.check("详情页展示状态与得分", "已完成" in detail_text, detail_text[:200])
            checker.check("详情页展示测试点明细", "测试点" in detail_text, detail_text[:200])

        print("\n=== 管理员用下拉框变更用户角色 ===")
        at.sidebar.radio[0].set_value("用户中心").run()
        role_options = list(at.selectbox(key="role_target").options)
        checker.check("用户管理下拉列出所有用户", len(role_options) >= 2, str(role_options))
        at.selectbox(key="role_target").set_value(victim_id)
        at.selectbox(key="role_value").set_value("admin")
        at.button(key="role_submit").click().run()
        checker.no_exception(at, "角色变更提交无异常")
        victim = api.get(f"{base}/api/users/{victim_id}", timeout=10)
        role = (victim.json().get("data") or {}).get("role") if victim.status_code == 200 else None
        checker.check("角色变更已生效", role == "admin", f"HTTP {victim.status_code} role={role}")

        print("\n=== 侧边栏 ===")
        sidebar_text = " ".join(str(x.value) for x in at.sidebar.markdown)
        checker.check("侧边栏显示当前用户", "admin" in page_text(at), sidebar_text[:120])

        print("\n" + "=" * 60)
        if checker.failures:
            print(f"通过 {checker.passed} 项，失败 {len(checker.failures)} 项：")
            for item in checker.failures:
                print(f"  - {item}")
            return 1
        print(f"前端测试全部通过（{checker.passed} 项）✅")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
