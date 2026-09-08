"""端到端测试：启动真实 uvicorn 服务，逐项校验 API 契约、权限、评测与 AI 链路。

用法：
    python -m tests.test_api            # 自动选择端口并清理临时数据目录

测试覆盖 Goal.md / API.md 中列出的所有接口与异常码，包括：
* 状态码优先级 401 > 403 > 400 > 429 > 409 > 404；
* 分页 / 筛选规则；
* 评测结果 AC/WA/TLE/MLE/RE/CE 与部分得分；
* 多语言（Python / C++）与动态注册语言；
* 评测日志可见性、访问审计；
* AI 智能命题全链路（含 SSE 实时进度、中断、Token 计费、导入题库）。
"""
from __future__ import annotations

import json
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

from tests import fake_llm_server  # noqa: E402

ADMIN = ("admin", "admintestpassword")


class Suite:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []
        self.section = ""

    def section_title(self, title: str) -> None:
        self.section = title
        print(f"\n=== {title} ===")

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  [PASS] {name}")
            return True
        self.failures.append(f"{self.section} / {name}: {detail}")
        print(f"  [FAIL] {name} -> {detail}")
        return False

    def eq(self, name: str, actual, expected) -> bool:
        return self.check(name, actual == expected, f"expected {expected!r}, got {actual!r}")

    def summary(self) -> int:
        total = self.passed + len(self.failures)
        print("\n" + "=" * 60)
        print(f"通过 {self.passed}/{total}")
        if self.failures:
            print("失败项：")
            for item in self.failures:
                print(f"  - {item}")
            return 1
        print("全部测试通过 ✅")
        return 0


class Client:
    """带 Cookie 会话的 API 客户端。"""

    def __init__(self, base: str, username: str = "", user_id: str = "") -> None:
        self.base = base
        self.session = requests.Session()
        self.username = username
        self.user_id = user_id

    def request(self, method: str, path: str, **kwargs) -> tuple[int, dict]:
        kwargs.setdefault("timeout", 30)
        resp = self.session.request(method, f"{self.base}{path}", **kwargs)
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        return resp.status_code, payload

    def get(self, path: str, **params):
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: dict | None = None):
        return self.request("POST", path, json=body if body is not None else {})

    def put(self, path: str, body: dict | None = None):
        return self.request("PUT", path, json=body if body is not None else {})

    def delete(self, path: str):
        return self.request("DELETE", path)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(data_dir: str, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["OJ_DATA_DIR"] = data_dir
    env["OJ_RESET_OPEN"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
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
            resp = requests.get(f"{base}/health", timeout=3)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.4)
    return False


def wait_submission(client: Client, submission_id: str, timeout: float = 90) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        _, payload = client.get(f"/api/submissions/{submission_id}")
        last = payload.get("data") or {}
        if last.get("status") != "pending":
            return last
        time.sleep(0.4)
    return last


def wait_ai_task(client: Client, task_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        _, payload = client.get(f"/api/ai/problem-tasks/{task_id}")
        last = payload.get("data") or {}
        if last.get("status") in ("success", "failed", "cancelled"):
            return last
        time.sleep(0.5)
    return last


# ---------------------------------------------------------------------------
PROBLEM = {
    "id": "p_ab",
    "title": "A+B Problem",
    "description": "输入两个整数 a, b，输出它们的和。",
    "input_description": "一行，两个整数 a 和 b。",
    "output_description": "输出 a+b。",
    "samples": [{"input": "1 2", "output": "3"}],
    "constraints": "|a|,|b| <= 10^9",
    "testcases": [{"input": "1 2\n", "output": "3\n"}, {"input": "-5 5\n", "output": "0\n"}],
    "hint": "有负数哦！",
    "source": "洛谷",
    "tags": ["基础题"],
    "time_limit": 1.0,
    "memory_limit": 128,
    "author": "Luogu",
    "difficulty": "入门",
}

AC_CODE = "a, b = map(int, input().split())\nprint(a + b)\n"
WA_CODE = "print(-1)\n"
PARTIAL_CODE = "a, b = map(int, input().split())\nprint(a + b if a + b == 3 else 42)\n"
RE_CODE = "print(1 / 0)\n"
TLE_CODE = "while True:\n    pass\n"
CE_CODE = "def broken(:\n    pass\n"
MLE_CODE = "chunks = []\nfor _ in range(100):\n    chunks.append(bytearray(10 * 1024 * 1024))\nprint('done')\n"
CPP_AC = (
    "#include <iostream>\n"
    "int main(){ long long a,b; std::cin>>a>>b; std::cout<<(a+b)<<std::endl; return 0; }\n"
)


class Harness:
    def __init__(self, base: str, suite: Suite) -> None:
        self.base = base
        self.suite = suite
        self._user_seq = 0

    def guest(self) -> Client:
        return Client(self.base)

    def login(self, username: str, password: str) -> Client:
        client = Client(self.base, username=username)
        status, payload = client.post("/api/auth/login", {"username": username, "password": password})
        assert status == 200, f"login failed for {username}: {status} {payload}"
        client.user_id = str((payload.get("data") or {}).get("user_id", ""))
        return client

    def admin(self) -> Client:
        return self.login(*ADMIN)

    def fresh_user(self, prefix: str = "u") -> Client:
        self._user_seq += 1
        name = f"{prefix}{self._user_seq:03d}"
        client = Client(self.base, username=name)
        status, payload = client.post("/api/users/", {"username": name, "password": "password123"})
        assert status == 200, f"register failed: {status} {payload}"
        return self.login(name, "password123")

    def submit(self, client: Client, code: str, language: str = "python",
               problem_id: str = "p_ab") -> tuple[int, dict]:
        return client.post("/api/submissions/", {
            "problem_id": problem_id, "language": language, "code": code,
        })


# ---------------------------------------------------------------------------
def test_users(h: Harness) -> None:
    s = h.suite
    s.section_title("Step 4 用户管理")

    admin = h.admin()
    status, payload = admin.get("/api/users/1")
    s.eq("初始管理员可查询自己", status, 200)
    s.eq("初始管理员角色", (payload.get("data") or {}).get("role"), "admin")
    s.check("用户信息不含密码", "password" not in json.dumps(payload), "响应中出现 password 字段")

    guest = h.guest()
    status, payload = guest.post("/api/users/", {"username": "alice", "password": "password123"})
    s.eq("注册成功", status, 200)
    s.eq("注册返回 role", (payload.get("data") or {}).get("role"), "user")
    s.eq("注册 submit_count", (payload.get("data") or {}).get("submit_count"), 0)
    alice_id = str((payload.get("data") or {}).get("user_id"))

    status, _ = guest.post("/api/users/", {"username": "alice", "password": "password123"})
    s.eq("重复用户名 -> 400", status, 400)
    status, _ = guest.post("/api/users/", {"username": "ab", "password": "password123"})
    s.eq("用户名过短 -> 400", status, 400)
    status, _ = guest.post("/api/users/", {"username": "alice2", "password": "123"})
    s.eq("密码过短 -> 400", status, 400)
    status, _ = guest.post("/api/users/", {"username": "alice3"})
    s.eq("缺少密码 -> 400", status, 400)

    status, _ = guest.post("/api/auth/login", {"username": "alice", "password": "wrong"})
    s.eq("密码错误 -> 401", status, 401)
    status, _ = guest.post("/api/auth/login", {"username": "nobody", "password": "password123"})
    s.eq("用户不存在 -> 401", status, 401)

    alice = h.login("alice", "password123")
    bob = h.fresh_user("bob")

    status, _ = guest.get("/api/users/")
    s.eq("未登录查询用户列表 -> 401", status, 401)
    status, _ = alice.get("/api/users/")
    s.eq("普通用户查询用户列表 -> 403", status, 403)
    status, payload = admin.get("/api/users/", page=1, page_size=2)
    s.eq("管理员查询用户列表", status, 200)
    s.check("用户列表含 total", "total" in (payload.get("data") or {}), str(payload))
    s.eq("分页生效", len((payload.get("data") or {}).get("users", [])), 2)
    status, _ = admin.get("/api/users/", page=1)
    s.eq("page 无 page_size -> 400", status, 400)

    status, _ = alice.get(f"/api/users/{alice_id}")
    s.eq("本人查询自己 -> 200", status, 200)
    status, _ = alice.get(f"/api/users/{bob.user_id}")
    s.eq("查询他人 -> 403", status, 403)
    status, _ = admin.get("/api/users/999999")
    s.eq("管理员查询不存在用户 -> 404", status, 404)

    status, _ = alice.put(f"/api/users/{bob.user_id}/role", {"role": "admin"})
    s.eq("普通用户改权限 -> 403", status, 403)
    status, _ = admin.put(f"/api/users/{bob.user_id}/role", {"role": "superuser"})
    s.eq("非法角色 -> 400", status, 400)
    status, _ = admin.put("/api/users/999999/role", {"role": "admin"})
    s.eq("变更不存在用户 -> 404", status, 404)
    status, payload = admin.put(f"/api/users/{bob.user_id}/role", {"role": "admin"})
    s.eq("管理员变更权限 -> 200", status, 200)
    s.eq("角色已更新", (payload.get("data") or {}).get("role"), "admin")

    status, _ = alice.post("/api/users/admin", {"username": "newadmin", "password": "password123"})
    s.eq("非管理员创建管理员 -> 403", status, 403)
    status, payload = admin.post("/api/users/admin", {"username": "newadmin", "password": "password123"})
    s.eq("管理员创建管理员 -> 200", status, 200)
    status, _ = admin.post("/api/users/admin", {"username": "newadmin", "password": "password123"})
    s.eq("重复创建管理员 -> 400", status, 400)

    # 禁用用户后不能再登录，且已有会话失效
    status, _ = admin.put(f"/api/users/{bob.user_id}/role", {"role": "banned"})
    s.eq("设置 banned -> 200", status, 200)
    status, _ = h.guest().post("/api/auth/login", {"username": bob.username, "password": "password123"})
    s.eq("banned 用户登录 -> 403", status, 403)
    status, _ = bob.get(f"/api/users/{bob.user_id}")
    s.eq("banned 用户已有会话 -> 403", status, 403)

    status, _ = alice.post("/api/auth/logout", {})
    s.eq("登出 -> 200", status, 200)
    status, _ = alice.get("/api/users/")
    s.eq("登出后 -> 401", status, 401)
    return {"alice_id": alice_id}


def test_problems(h: Harness, alice: Client, admin: Client) -> None:
    s = h.suite
    s.section_title("Step 1 题目管理")

    guest = h.guest()
    status, _ = guest.get("/api/problems/")
    s.eq("未登录查看题目列表 -> 401", status, 401)
    status, _ = guest.post("/api/problems/", PROBLEM)
    s.eq("未登录添加题目 -> 401", status, 401)

    status, payload = alice.post("/api/problems/", PROBLEM)
    s.eq("添加题目 -> 200", status, 200)
    s.eq("添加返回 id", (payload.get("data") or {}).get("id"), "p_ab")

    status, _ = alice.post("/api/problems/", PROBLEM)
    s.eq("重复 id -> 409", status, 409)

    broken = dict(PROBLEM, id="p_bad")
    broken.pop("testcases")
    status, _ = alice.post("/api/problems/", broken)
    s.eq("缺少必填字段 -> 400", status, 400)
    bad_id = dict(PROBLEM, id="../evil")
    status, _ = alice.post("/api/problems/", bad_id)
    s.eq("非法 id -> 400", status, 400)
    bad_cases = dict(PROBLEM, id="p_bad2", testcases=[{"input": "1"}])
    status, _ = alice.post("/api/problems/", bad_cases)
    s.eq("测试点字段缺失 -> 400", status, 400)

    status, payload = alice.get("/api/problems/")
    s.eq("查看题目列表 -> 200", status, 200)
    ids = [item["id"] for item in payload.get("data") or []]
    s.check("列表包含 p_ab", "p_ab" in ids, str(ids))

    status, payload = alice.get("/api/problems/p_ab")
    s.eq("查看题目详情 -> 200", status, 200)
    data = payload.get("data") or {}
    s.eq("详情返回 title", data.get("title"), "A+B Problem")
    s.eq("详情默认 hint", data.get("hint"), "有负数哦！")
    s.check("详情包含 testcases", isinstance(data.get("testcases"), list), str(data.get("testcases")))

    # 默认值补全：新建一个只给必填字段的题目
    minimal = {
        "id": "p_min", "title": "最小题目", "description": "d",
        "input_description": "i", "output_description": "o",
        "samples": [], "constraints": "c", "testcases": [],
    }
    status, _ = alice.post("/api/problems/", minimal)
    s.eq("仅必填字段也可创建", status, 200)
    _, payload = alice.get("/api/problems/p_min")
    data = payload.get("data") or {}
    s.eq("默认 hint 为 ''", data.get("hint"), "")
    s.eq("默认 tags 为 []", data.get("tags"), [])
    s.eq("默认 time_limit 为 3.0", data.get("time_limit"), 3.0)
    s.eq("默认 memory_limit 为 128", data.get("memory_limit"), 128)
    alice.delete("/api/problems/p_min")

    mismatch = dict(PROBLEM, id="p_other")
    status, _ = alice.put("/api/problems/p_ab", mismatch)
    s.eq("body.id 与路径不一致 -> 400", status, 400)
    status, _ = alice.put("/api/problems/p_missing", dict(PROBLEM, id="p_missing"))
    s.eq("编辑不存在题目 -> 404", status, 404)

    updated = dict(PROBLEM, title="A+B Problem (edited)")
    status, payload = alice.put("/api/problems/p_ab", updated)
    s.eq("编辑题目 -> 200", status, 200)
    _, payload = alice.get("/api/problems/p_ab")
    s.eq("编辑已生效", (payload.get("data") or {}).get("title"), "A+B Problem (edited)")

    status, _ = alice.delete("/api/problems/p_ab")
    s.eq("普通用户删除题目 -> 403", status, 403)
    status, _ = guest.delete("/api/problems/p_ab")
    s.eq("未登录删除题目 -> 401", status, 401)
    status, _ = admin.delete("/api/problems/no_such")
    s.eq("删除不存在题目 -> 404", status, 404)
    status, payload = admin.delete("/api/problems/p_ab")
    s.eq("管理员删除题目 -> 200", status, 200)
    s.eq("删除返回 id", (payload.get("data") or {}).get("id"), "p_ab")
    status, _ = admin.delete("/api/problems/p_ab")
    s.eq("重复删除 -> 404", status, 404)
    status, _ = alice.get("/api/problems/p_ab")
    s.eq("查询已删除题目 -> 404", status, 404)

    # 恢复题目供后续评测使用
    alice.post("/api/problems/", PROBLEM)


def test_languages(h: Harness, alice: Client) -> None:
    s = h.suite
    s.section_title("Step 2 语言管理")

    status, payload = h.guest().get("/api/languages/")
    s.eq("查询语言列表（公开）", status, 200)
    names = (payload.get("data") or {}).get("name", [])
    s.check("内置 python", "python" in names, str(names))
    s.check("内置 cpp", "cpp" in names, str(names))

    status, _ = h.guest().post("/api/languages/", {"name": "go", "file_ext": ".go", "run_cmd": "go run {src}"})
    s.eq("未登录注册语言 -> 401", status, 401)

    status, payload = alice.post("/api/languages/", {
        "name": "nodejs", "file_ext": ".js", "run_cmd": "node {src}",
        "time_limit": 2.0, "memory_limit": 256,
    })
    s.eq("注册新语言 -> 200", status, 200)
    s.eq("注册返回 name", (payload.get("data") or {}).get("name"), "nodejs")

    status, _ = alice.post("/api/languages/", {"name": "shell", "file_ext": ".sh", "run_cmd": "bash {src}"})
    s.eq("禁止 shell 解释器 -> 400", status, 400)
    status, _ = alice.post("/api/languages/", {"name": "evil", "file_ext": ".py",
                                               "run_cmd": "python {src}; rm -rf /"})
    s.eq("禁止命令注入字符 -> 400", status, 400)
    status, _ = alice.post("/api/languages/", {"name": "bad", "file_ext": ".py"})
    s.eq("缺少 run_cmd -> 400", status, 400)
    status, _ = alice.post("/api/languages/", {"name": "bad", "file_ext": "py", "run_cmd": "python {src}"})
    s.eq("非法扩展名 -> 400", status, 400)

    _, payload = alice.get("/api/languages/")
    s.check("列表包含新注册语言", "nodejs" in (payload.get("data") or {}).get("name", []),
            str(payload))


def test_judge(h: Harness, admin: Client) -> None:
    s = h.suite
    s.section_title("Step 2 评测引擎")

    # 每个用例使用独立用户，避免触发 1 分钟 3 次的频率限制
    cases = [
        ("AC", AC_CODE, "python", 20, 20),
        ("WA", WA_CODE, "python", 0, 20),
        ("部分通过", PARTIAL_CODE, "python", 10, 20),
        ("RE", RE_CODE, "python", 0, 20),
        ("TLE", TLE_CODE, "python", 0, 20),
        ("CE", CE_CODE, "python", 0, 20),
        ("C++ AC", CPP_AC, "cpp", 20, 20),
    ]
    seen: dict[str, tuple[Client, str]] = {}
    for label, code, language, expect_score, expect_counts in cases:
        client = h.fresh_user("judge")
        status, payload = h.submit(client, code, language)
        if not s.eq(f"{label} 提交返回 200", status, 200):
            continue
        submission_id = str((payload.get("data") or {}).get("submission_id"))
        seen[label] = (client, submission_id)
        s.eq(f"{label} 提交时状态为 pending", (payload.get("data") or {}).get("status"), "pending")
        detail = wait_submission(client, submission_id)
        s.eq(f"{label} 评测状态 success", detail.get("status"), "success")
        s.eq(f"{label} 得分", detail.get("score"), expect_score)
        s.eq(f"{label} 总分", detail.get("counts"), expect_counts)
        if label == "CE":
            s.eq("CE 编译信息 result", (detail.get("compile_info") or {}).get("result"), "failed")
        if label == "AC":
            s.eq("AC 编译信息为 null（解释型语言）", detail.get("compile_info"), None)
            s.eq("AC 运行信息", (detail.get("run_info") or {}).get("result"), "finished")
            s.eq("AC 错误信息为空", detail.get("error_info"), "")

    # 用管理员权限读取评测日志，确认测试点级别的判定结果
    def case_results(label: str) -> list[str]:
        _, submission_id = seen.get(label, (None, None))
        if submission_id is None:
            return []
        status, payload = admin.get(f"/api/submissions/{submission_id}/log")
        if status != 200:
            return []
        return [d.get("result") for d in (payload.get("data") or {}).get("details") or []]

    s.eq("AC 测试点结果", case_results("AC"), ["AC", "AC"])
    s.eq("WA 测试点结果", case_results("WA"), ["WA", "WA"])
    s.eq("部分通过测试点结果", case_results("部分通过"), ["AC", "WA"])
    s.eq("TLE 测试点结果", case_results("TLE"), ["TLE", "TLE"])
    s.eq("RE 测试点结果", case_results("RE"), ["RE", "RE"])
    s.eq("CE 无测试点结果", case_results("CE"), [])

    # MLE
    mle_problem = dict(PROBLEM, id="p_mle", title="内存限制题", memory_limit=64, time_limit=5.0)
    admin.post("/api/problems/", mle_problem)
    client = h.fresh_user("judge")
    status, payload = h.submit(client, MLE_CODE, "python", problem_id="p_mle")
    if s.eq("MLE 提交返回 200", status, 200):
        mle_id = str((payload.get("data") or {}).get("submission_id"))
        detail = wait_submission(client, mle_id)
        s.eq("MLE 得分 0", detail.get("score"), 0)
        _, log_payload = admin.get(f"/api/submissions/{mle_id}/log")
        results = [d.get("result") for d in (log_payload.get("data") or {}).get("details") or []]
        s.check("MLE 判定为 MLE", "MLE" in results, str(results))

    # 提交异常
    client = h.fresh_user("judge")
    status, _ = h.submit(client, AC_CODE, "python", problem_id="no_such_problem")
    s.eq("题目不存在 -> 404", status, 404)
    status, _ = h.submit(client, AC_CODE, "no_such_language")
    s.eq("语言不存在 -> 404", status, 404)
    status, _ = client.post("/api/submissions/", {"problem_id": "p_ab", "language": "python"})
    s.eq("缺少 code -> 400", status, 400)
    status, _ = h.guest().post("/api/submissions/", {
        "problem_id": "p_ab", "language": "python", "code": AC_CODE})
    s.eq("未登录提交 -> 401", status, 401)

    # 频率限制：同一用户 1 分钟内第 4 次提交 -> 429
    ratelimit_user = h.fresh_user("rate")
    statuses = [h.submit(ratelimit_user, AC_CODE)[0] for _ in range(4)]
    s.check("前三次提交成功", statuses[:3] == [200, 200, 200], str(statuses))
    s.eq("第 4 次提交 -> 429", statuses[3], 429)

    # 优先级：未登录 + 参数错误 -> 401（而不是 400）
    status, _ = h.guest().post("/api/submissions/", {"problem_id": "p_ab"})
    s.eq("未登录 + 缺参数 -> 401", status, 401)
    # 优先级：登录 + 参数错误 -> 400（而不是 429/404）
    status, _ = h.submit(ratelimit_user, "", "python", problem_id="no_such_problem")
    s.eq("已登录 + 空代码 + 题目不存在 -> 400", status, 400)


def test_submission_management(h: Harness, admin: Client) -> None:
    s = h.suite
    s.section_title("Step 3 评测管理")

    owner = h.fresh_user("sub")
    status, payload = h.submit(owner, AC_CODE)
    submission_id = str((payload.get("data") or {}).get("submission_id"))
    wait_submission(owner, submission_id)

    other = h.fresh_user("sub")
    status, _ = owner.get("/api/submissions/")
    s.eq("一级条件全空 -> 400", status, 400)
    status, _ = owner.get("/api/submissions/", page=1)
    s.eq("page 无 page_size -> 400", status, 400)
    status, payload = owner.get("/api/submissions/", problem_id="p_ab", page_size=1)
    s.eq("page_size 单独出现按第一页处理", status, 200)
    s.check("返回不超过 page_size 条", len((payload.get("data") or {}).get("submissions", [])) <= 1,
            str(payload))
    status, _ = owner.get("/api/submissions/", problem_id="p_ab", status="unknown")
    s.eq("非法 status -> 400", status, 400)

    status, payload = owner.get("/api/submissions/", problem_id="p_ab")
    s.eq("按题目查询自己的提交", status, 200)
    records = (payload.get("data") or {}).get("submissions", [])
    s.check("列表摘要包含自己的提交", any(r["submission_id"] == submission_id for r in records), str(records))
    s.check("pending/error 摘要只有基础字段",
            all(set(r.keys()) <= {"submission_id", "status", "score", "counts"} for r in records),
            str(records))

    status, payload = other.get("/api/submissions/", problem_id="p_ab")
    s.eq("其他用户查询该题 -> 200（仅自己记录）", status, 200)
    others = (payload.get("data") or {}).get("submissions", [])
    s.check("其他用户看不到别人的提交",
            all(r["submission_id"] != submission_id for r in others), str(others))

    status, payload = admin.get("/api/submissions/", problem_id="p_ab", page=1, page_size=5)
    s.eq("管理员查询该题全部提交", status, 200)
    s.check("管理员能看到所有用户", (payload.get("data") or {}).get("total", 0) >= 1, str(payload))

    status, _ = owner.get("/api/submissions/", user_id="no_such_user")
    s.eq("user_id 不存在返回空列表", status, 200)

    status, _ = other.get(f"/api/submissions/{submission_id}")
    s.eq("非本人查看详情 -> 403", status, 403)
    status, _ = admin.get(f"/api/submissions/{submission_id}")
    s.eq("管理员查看详情 -> 200", status, 200)
    status, _ = owner.get("/api/submissions/999999")
    s.eq("查看不存在评测 -> 404", status, 404)
    status, payload = owner.get(f"/api/submissions/{submission_id}")
    data = payload.get("data") or {}
    s.check("详情包含编译/运行/错误信息字段",
            all(k in data for k in ("compile_info", "run_info", "error_info")), str(data))

    status, _ = other.put(f"/api/submissions/{submission_id}/rejudge", {})
    s.eq("普通用户重新评测 -> 403", status, 403)
    status, _ = h.guest().put(f"/api/submissions/{submission_id}/rejudge", {})
    s.eq("未登录重新评测 -> 401", status, 401)
    status, _ = admin.put("/api/submissions/999999/rejudge", {})
    s.eq("重新评测不存在 -> 404", status, 404)
    status, payload = admin.put(f"/api/submissions/{submission_id}/rejudge", {})
    s.eq("管理员重新评测 -> 200", status, 200)
    s.eq("重新评测后状态 pending", (payload.get("data") or {}).get("status"), "pending")
    detail = wait_submission(owner, submission_id)
    s.eq("重新评测后再次成功", detail.get("status"), "success")


def test_logs(h: Harness, admin: Client) -> None:
    s = h.suite
    s.section_title("Step 5 评测日志与审计")

    owner = h.fresh_user("log")
    status, payload = h.submit(owner, AC_CODE)
    submission_id = str((payload.get("data") or {}).get("submission_id"))
    wait_submission(owner, submission_id)
    other = h.fresh_user("log")

    status, payload = owner.get(f"/api/submissions/{submission_id}/log")
    s.eq("本人查询日志（未公开）-> 200", status, 200)
    data = payload.get("data") or {}
    s.check("未公开时不含 details", "details" not in data, str(data))
    s.eq("日志返回 counts", data.get("counts"), 20)

    status, _ = other.get(f"/api/submissions/{submission_id}/log")
    s.eq("他人查询未公开日志 -> 403", status, 403)
    status, _ = h.guest().get(f"/api/submissions/{submission_id}/log")
    s.eq("未登录查询日志 -> 401", status, 401)
    status, _ = admin.get("/api/submissions/999999/log")
    s.eq("查询不存在评测的日志 -> 404", status, 404)

    status, _ = other.put("/api/problems/p_ab/log_visibility", {"public_cases": True})
    s.eq("非管理员配置可见性 -> 403", status, 403)
    status, _ = admin.put("/api/problems/no_such/log_visibility", {"public_cases": True})
    s.eq("配置不存在题目 -> 404", status, 404)
    status, _ = admin.put("/api/problems/p_ab/log_visibility", {"public_cases": "yes"})
    s.eq("public_cases 非布尔 -> 400", status, 400)
    status, payload = admin.put("/api/problems/p_ab/log_visibility", {"public_cases": True})
    s.eq("管理员配置可见性 -> 200", status, 200)
    s.eq("返回 public_cases", (payload.get("data") or {}).get("public_cases"), True)

    status, payload = owner.get(f"/api/submissions/{submission_id}/log")
    data = payload.get("data") or {}
    s.eq("公开后本人可见 details", status, 200)
    s.check("details 是列表", isinstance(data.get("details"), list), str(data))
    s.check("details 含测例字段",
            all(set(d) >= {"id", "result", "time", "memory"} for d in data.get("details", [])),
            str(data.get("details")))
    status, payload = other.get(f"/api/submissions/{submission_id}/log")
    s.eq("公开后其他登录用户可见", status, 200)
    s.check("其他用户可见 details", isinstance((payload.get("data") or {}).get("details"), list), str(payload))

    status, _ = owner.get("/api/logs/access/")
    s.eq("非管理员查询审计 -> 403", status, 403)
    status, payload = admin.get("/api/logs/access/", problem_id="p_ab")
    s.eq("管理员查询审计 -> 200", status, 200)
    logs = payload.get("data") or []
    s.check("审计记录包含 action", all(item.get("action") == "view_logs" for item in logs), str(logs[:3]))
    s.check("审计记录包含 status 字段", all("status" in item for item in logs), str(logs[:3]))
    s.check("记录了 403 的访问", any(item.get("status") == "403" for item in logs), str(logs[:5]))
    s.check("记录了 200 的访问", any(item.get("status") == "200" for item in logs), str(logs[:5]))
    s.check("审计不记录未登录访问", all(item.get("user_id") for item in logs), str(logs[:5]))

    admin.put("/api/problems/p_ab/log_visibility", {"public_cases": False})


def test_ai(h: Harness, admin: Client, fake_port: int) -> None:
    s = h.suite
    s.section_title("Advance AI 智能命题")

    user = h.fresh_user("ai")
    status, payload = user.get("/api/ai/model-config")
    s.eq("查询模型配置 -> 200", status, 200)
    s.eq("初始未配置密钥", (payload.get("data") or {}).get("api_key_configured"), False)

    status, _ = user.put("/api/ai/model-config", {
        "provider_url": "http://127.0.0.1:1/v1", "model": "x"})
    s.eq("首次配置缺少 api_key -> 400", status, 400)
    status, _ = user.put("/api/ai/model-config", {
        "provider_url": "not-a-url", "model": "x", "api_key": "k"})
    s.eq("非法 provider_url -> 400", status, 400)

    status, payload = user.put("/api/ai/model-config", {
        "provider_url": f"http://127.0.0.1:{fake_port}/v1",
        "model": "fake-model",
        "api_key": "sk-test-secret-key",
        "input_price": 1.0,
        "output_price": 2.0,
        "price_unit": 1000000,
    })
    s.eq("保存模型配置 -> 200", status, 200)
    data = payload.get("data") or {}
    s.eq("配置返回 api_key_configured", data.get("api_key_configured"), True)
    s.check("响应不含密钥明文", "sk-test-secret-key" not in json.dumps(payload), json.dumps(payload))
    _, payload = user.get("/api/ai/model-config")
    s.check("查询接口不含密钥", "api_key" not in (payload.get("data") or {})
            or (payload.get("data") or {}).get("api_key") in (None, ""), json.dumps(payload))

    status, _ = user.post("/api/ai/problem-tasks/", {"problem_id": "p_ab"})
    s.eq("缺少 requirement -> 400", status, 400)
    status, _ = user.post("/api/ai/problem-tasks/", {
        "requirement": "随便出一道题", "problem_id": "no_such_problem"})
    s.eq("指定题目不存在 -> 404", status, 404)
    status, _ = h.guest().post("/api/ai/problem-tasks/", {"requirement": "x"})
    s.eq("未登录创建任务 -> 401", status, 401)

    # 正常任务：实时观察（SSE）
    status, payload = user.post("/api/ai/problem-tasks/", {
        "requirement": "为「循环与数组求和」这一节课设计一道入门题，要求考察读入 n 个整数并求和",
        "difficulty": "入门",
        "knowledge_points": ["循环", "输入输出"],
        "case_count": 5,
    })
    s.eq("创建命题任务 -> 200", status, 200)
    task_id = str((payload.get("data") or {}).get("task_id"))
    s.eq("任务初始状态", (payload.get("data") or {}).get("status"), "pending")

    events: list[str] = []
    try:
        with user.session.get(
            f"{h.base}/api/ai/problem-tasks/{task_id}/events", stream=True, timeout=(10, 120)
        ) as resp:
            event_name = ""
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                line = raw.strip()
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:") and event_name:
                    events.append(event_name)
                    if event_name == "status":
                        body = json.loads(line[5:].strip())
                        if body.get("status") in ("success", "failed", "cancelled"):
                            break
    except requests.RequestException as exc:
        s.check("SSE 连接可用", False, str(exc))
    s.check("SSE 收到进度事件", "progress" in events, str(events[:10]))
    s.check("SSE 收到状态事件", "status" in events, str(events[:10]))

    task = wait_ai_task(user, task_id)
    s.eq("任务最终状态 success", task.get("status"), "success")
    s.check("任务有分阶段进度记录", len(task.get("stages") or []) >= 3, str(task.get("stages")))
    result = task.get("result") or {}
    problem = result.get("problem") or {}
    s.eq("生成题目 id", problem.get("id"), "ai_sum_array")
    s.check("生成题目包含测试点", len(problem.get("testcases") or []) >= 3,
            str(len(problem.get("testcases") or [])))
    s.check("测试点含输入输出", all("input" in c and "output" in c for c in problem.get("testcases") or []),
            str(problem.get("testcases")[:2]))
    verification = result.get("verification") or {}
    s.eq("测试数据校验通过", verification.get("passed"), True)
    s.check("校验覆盖小数据与大规模数据",
            verification.get("small_cases", 0) >= 1 and verification.get("large_cases", 0) >= 1,
            str(verification))

    usage = task.get("usage") or {}
    s.check("统计到输入 Token", usage.get("input_tokens", 0) > 0, str(usage))
    s.check("统计到输出 Token", usage.get("output_tokens", 0) > 0, str(usage))
    s.check("总 Token 等于输入+输出",
            usage.get("total_tokens") == usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            str(usage))
    s.check("费用按单价计算正确", abs(usage.get("cost", 0) - 0.0028) < 1e-9, str(usage))

    # 权限：其他用户不能查看
    stranger = h.fresh_user("ai")
    status, _ = stranger.get(f"/api/ai/problem-tasks/{task_id}")
    s.eq("他人查询任务 -> 403", status, 403)
    status, _ = admin.get(f"/api/ai/problem-tasks/{task_id}")
    s.eq("管理员查询任务 -> 200", status, 200)
    status, _ = stranger.get("/api/ai/problem-tasks/no-such-task")
    s.eq("任务不存在 -> 404", status, 404)

    # 导入题库
    status, payload = user.post(f"/api/ai/problem-tasks/{task_id}/apply", {"mode": "create"})
    s.eq("导入题库 -> 200", status, 200)
    s.eq("导入返回题目 id", (payload.get("data") or {}).get("id"), "ai_sum_array")
    status, _ = user.post(f"/api/ai/problem-tasks/{task_id}/apply", {"mode": "create"})
    s.eq("重复导入 -> 409", status, 409)
    status, _ = user.post(f"/api/ai/problem-tasks/{task_id}/apply", {"mode": "update"})
    s.eq("以 update 模式覆盖 -> 200", status, 200)

    # 用 AI 生成的参考程序提交到 AI 生成的题目，应当 AC
    solver = h.fresh_user("solve")
    status, payload = h.submit(solver, result.get("reference_code", ""), "python",
                              problem_id="ai_sum_array")
    s.eq("提交 AI 参考程序 -> 200", status, 200)
    detail = wait_submission(solver, str((payload.get("data") or {}).get("submission_id")))
    s.eq("AI 参考程序 AC（满分）", detail.get("score"), detail.get("counts"))
    s.check("满分非零", (detail.get("score") or 0) > 0, str(detail))

    # 错误程序应当被测试点抓住
    wrong = h.fresh_user("solve")
    status, payload = h.submit(wrong, "print(0)\n", "python", problem_id="ai_sum_array")
    detail = wait_submission(wrong, str((payload.get("data") or {}).get("submission_id")))
    s.eq("错误程序得分 0", detail.get("score"), 0)

    # 中断任务
    status, payload = user.post("/api/ai/problem-tasks/", {
        "requirement": "慢速测试：请设计一道需要较长时间的题目",
        "case_count": 5,
    })
    slow_id = str((payload.get("data") or {}).get("task_id"))
    time.sleep(2.0)
    status, payload = user.put(f"/api/ai/problem-tasks/{slow_id}/cancel", {})
    s.eq("中断任务 -> 200", status, 200)
    s.eq("中断后状态 cancelled", (payload.get("data") or {}).get("status"), "cancelled")
    time.sleep(1.0)
    _, payload = user.get(f"/api/ai/problem-tasks/{slow_id}")
    s.eq("中断后任务不再运行", (payload.get("data") or {}).get("status"), "cancelled")
    status, _ = user.put(f"/api/ai/problem-tasks/{slow_id}/cancel", {})
    s.eq("重复中断已结束任务 -> 409", status, 409)

    status, payload = user.get("/api/ai/problem-tasks/")
    s.eq("任务列表 -> 200", status, 200)
    s.check("任务列表非空", len(payload.get("data") or []) >= 2, str(payload)[:200])


def test_reset(h: Harness) -> None:
    s = h.suite
    s.section_title("系统重置")
    guest = h.guest()
    status, _ = guest.post("/api/reset/", {})
    s.eq("未登录重置 -> 401", status, 401)

    admin = h.admin()
    status, payload = admin.post("/api/reset/", {})
    s.eq("管理员重置 -> 200", status, 200)
    s.eq("重置返回消息", payload.get("msg"), "system reset successfully")

    status, _ = admin.get("/api/problems/")
    s.eq("重置会退出当前登录状态 -> 401", status, 401)

    admin = h.admin()  # 重置后重新登录
    status, payload = admin.get("/api/problems/")
    s.eq("重置后题目列表为空", payload.get("data"), [])
    status, payload = admin.get("/api/languages/")
    names = (payload.get("data") or {}).get("name", [])
    s.check("重置后恢复内置语言", "python" in names and "cpp" in names, str(names))
    status, payload = admin.get("/api/users/")
    s.eq("重置后只剩初始管理员", (payload.get("data") or {}).get("total"), 1)
    status, payload = h.guest().post("/api/auth/login", {"username": ADMIN[0], "password": ADMIN[1]})
    s.eq("重置后可重新登录初始管理员", status, 200)


def main() -> int:
    suite = Suite()
    data_dir = tempfile.mkdtemp(prefix="oj_test_")
    port = free_port()
    fake_port = free_port()
    base = f"http://127.0.0.1:{port}"

    print(f"数据目录：{data_dir}")
    print(f"后端地址：{base}")
    print(f"假模型服务：http://127.0.0.1:{fake_port}/v1")

    fake = fake_llm_server.start(fake_port)
    proc = start_server(data_dir, port)
    try:
        if not wait_health(base):
            print("服务启动失败，日志：")
            print((Path(data_dir) / "server.log").read_text(encoding="utf-8", errors="replace"))
            return 2

        h = Harness(base, suite)
        test_users(h)
        admin = h.admin()
        alice = h.login("alice", "password123")
        test_problems(h, alice, admin)
        test_languages(h, alice)
        test_judge(h, admin)
        test_submission_management(h, admin)
        test_logs(h, admin)
        test_ai(h, admin, fake_port)
        test_reset(h)
        return suite.summary()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        fake.shutdown()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
