"""前端冒烟测试：用 Streamlit 官方 AppTest 真正执行页面脚本。

检查点：
* 每个页面组都能正常渲染，不抛异常；
* 登录表单能通过 REST API 完成认证，登录后页面进入已登录状态；
* 题目列表、提交记录等页面能正确展示后端返回的数据。
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


def main() -> int:
    from streamlit.testing.v1 import AppTest

    data_dir = tempfile.mkdtemp(prefix="oj_front_")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    os.environ["OJ_API_BASE"] = base
    proc = start_backend(data_dir, port)
    failures: list[str] = []
    passed = 0
    try:
        if not wait_health(base):
            print("后端启动失败")
            print((Path(data_dir) / "server.log").read_text(encoding="utf-8", errors="replace"))
            return 2

        # 预置一个题目，便于题目/评测页面有数据可展示
        session = requests.Session()
        session.post(f"{base}/api/auth/login",
                     json={"username": "admin", "password": "admintestpassword"}, timeout=10)
        session.post(f"{base}/api/problems/", json={
            "id": "p_front", "title": "前端测试题", "description": "求 a+b",
            "input_description": "两个整数", "output_description": "和",
            "samples": [{"input": "1 2", "output": "3"}], "constraints": "|a|,|b|<=1e9",
            "testcases": [{"input": "1 2\n", "output": "3\n"}],
        }, timeout=10)

        at = AppTest.from_file(APP, default_timeout=60)
        at.session_state["api_base"] = base
        at.run()
        if at.exception:
            failures.append(f"首页渲染异常：{at.exception[0].value}")
        else:
            passed += 1
            print("  [PASS] 首页渲染无异常")

        # 逐页切换
        pages = ["用户中心", "题库", "评测中心", "AI 智能命题"]
        for page in pages:
            at.session_state["api_base"] = base
            at.sidebar.radio[0].set_value(page).run()
            if at.exception:
                failures.append(f"{page} 页面异常：{at.exception[0].value}")
            else:
                passed += 1
                print(f"  [PASS] {page} 页面渲染无异常")

        # 登录流程
        at.session_state["api_base"] = base
        at.sidebar.radio[0].set_value("用户中心").run()
        at.text_input(key="login_username").set_value("admin")
        at.text_input(key="login_password").set_value("admintestpassword")
        at.button(key="login_submit").click().run()
        if at.exception:
            failures.append(f"登录流程异常：{at.exception[0].value}")
        elif _state_user(at) is None:
            failures.append("登录后 session_state 中没有用户信息")
        else:
            passed += 1
            print(f"  [PASS] 登录成功：{_state_user(at)}")

        # 登录后再次遍历页面（此时用户管理、删除题目等管理员入口出现）
        for page in pages:
            at.sidebar.radio[0].set_value(page).run()
            if at.exception:
                failures.append(f"登录后 {page} 页面异常：{at.exception[0].value}")
            else:
                passed += 1
                print(f"  [PASS] 登录后 {page} 页面渲染无异常")

        # 题目列表页应展示后端返回的题目
        at.sidebar.radio[0].set_value("题库").run()
        rendered = " ".join(str(x.value) for x in at.markdown) + " ".join(
            str(x.value) for x in at.dataframe)
        if "p_front" in rendered or "前端测试题" in rendered:
            passed += 1
            print("  [PASS] 题目列表展示后端数据")
        else:
            failures.append("题目列表未展示后端数据")

        print("\n" + "=" * 60)
        if failures:
            print(f"通过 {passed} 项，失败 {len(failures)} 项：")
            for item in failures:
                print(f"  - {item}")
            return 1
        print(f"前端测试全部通过（{passed} 项）✅")
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
