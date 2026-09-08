"""一键启动脚本。

用法：
    python run.py backend            # 启动 FastAPI 后端（默认 127.0.0.1:8000）
    python run.py frontend           # 启动 Streamlit 前端（默认 8501）
    python run.py test               # 运行端到端测试
    python run.py test-frontend      # 运行前端冒烟测试
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def backend(port: int = 8000, reload: bool = False) -> int:
    cmd = [sys.executable, "-m", "uvicorn", "backend.app:app",
           "--host", "127.0.0.1", "--port", str(port)]
    if reload:
        cmd.append("--reload")
    print(f"启动后端：http://127.0.0.1:{port}（接口文档 /docs）")
    return subprocess.call(cmd, cwd=str(ROOT))


def frontend(port: int = 8501, api_base: str = "http://127.0.0.1:8000") -> int:
    env = dict(os.environ)
    env.setdefault("OJ_API_BASE", api_base)
    print(f"启动前端：http://127.0.0.1:{port}（后端 {env['OJ_API_BASE']}）")
    return subprocess.call(
        [sys.executable, "-m", "streamlit", "run", "frontend/app.py",
         "--server.port", str(port), "--server.headless", "true"],
        cwd=str(ROOT), env=env,
    )


def main() -> int:
    args = sys.argv[1:]
    action = args[0] if args else "backend"
    port = int(args[1]) if len(args) > 1 else None

    if action == "backend":
        return backend(port or 8000, reload="--reload" in args)
    if action == "frontend":
        return frontend(port or 8501)
    if action == "test":
        return subprocess.call([sys.executable, "-m", "tests.test_api"], cwd=str(ROOT))
    if action == "test-frontend":
        return subprocess.call([sys.executable, "-m", "tests.test_frontend"], cwd=str(ROOT))
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
