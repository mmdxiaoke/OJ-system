"""把示例题目导入正在运行的后端。

用法：
    python examples/load_problems.py [后端地址]

默认后端地址为 http://127.0.0.1:8000，会以初始管理员身份登录后导入
examples/sample_problems.json 中的题目。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DATA_FILE = Path(__file__).resolve().parent / "sample_problems.json"


def main() -> int:
    problems = json.loads(DATA_FILE.read_text(encoding="utf-8"))["problems"]
    session = requests.Session()
    resp = session.post(
        f"{BASE}/api/auth/login",
        json={"username": "admin", "password": "admintestpassword"},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"登录失败：{resp.status_code} {resp.text}")
        return 1
    print("已登录 admin")

    for problem in problems:
        resp = session.post(f"{BASE}/api/problems/", json=problem, timeout=10)
        payload = resp.json()
        if resp.status_code == 200:
            print(f"  导入成功：{payload['data']['id']}")
        elif resp.status_code == 409:
            resp = session.put(f"{BASE}/api/problems/{problem['id']}", json=problem, timeout=10)
            print(f"  已存在，改为覆盖：{problem['id']} -> {resp.status_code}")
        else:
            print(f"  导入失败：{problem['id']} -> {resp.status_code} {payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
