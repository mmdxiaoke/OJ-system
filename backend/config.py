"""全局配置。

所有可调参数集中在这里，避免散落在业务代码中。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

#: 数据目录，可通过环境变量 OJ_DATA_DIR 覆盖（测试时非常有用）
DATA_DIR = Path(os.environ.get("OJ_DATA_DIR") or (BASE_DIR / "data")).resolve()

PROBLEM_DIR = DATA_DIR / "problems"
SUBMISSION_DIR = DATA_DIR / "submissions"
AI_TASK_DIR = DATA_DIR / "ai_tasks"

USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
LANGUAGES_FILE = DATA_DIR / "languages.json"
ACCESS_LOG_FILE = DATA_DIR / "access_logs.json"
AI_CONFIG_FILE = DATA_DIR / "ai_config.json"
AI_TASKS_INDEX_FILE = DATA_DIR / "ai_tasks.json"
SECRET_FILE = DATA_DIR / "secret.key"

DATA_DIRS = [DATA_DIR, PROBLEM_DIR, SUBMISSION_DIR, AI_TASK_DIR]

# ---------------------------------------------------------------------------
# 评测默认值
# ---------------------------------------------------------------------------
DEFAULT_TIME_LIMIT: float = 3.0          # 秒
DEFAULT_MEMORY_LIMIT: int = 128          # MB
SCORE_PER_TESTCASE: int = 10             # 每个测试点 10 分

#: 单个测试点允许的最大输出长度（防止用户代码疯狂输出撑爆内存）
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
#: 编译时间上限
COMPILE_TIME_LIMIT: float = 10.0
#: 内存监控轮询间隔（Windows / 无 rlimit 平台）
MEMORY_POLL_INTERVAL: float = 0.02

# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------
SESSION_COOKIE_NAME = "oj_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600      # 7 天
SESSION_HTTPS_ONLY = os.environ.get("OJ_SESSION_HTTPS", "0") == "1"

# ---------------------------------------------------------------------------
# 初始管理员
# ---------------------------------------------------------------------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admintestpassword"

# ---------------------------------------------------------------------------
# 用户名校验
# ---------------------------------------------------------------------------
USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 40
PASSWORD_MIN_LEN = 6

# ---------------------------------------------------------------------------
# 提交频率限制：60 秒内最多 3 次
# ---------------------------------------------------------------------------
SUBMIT_RATE_WINDOW = 60.0
SUBMIT_RATE_MAX = 3

# ---------------------------------------------------------------------------
# 其他
# ---------------------------------------------------------------------------
VALID_ROLES = ("user", "admin", "banned")

#: 默认 Python 解释器。Linux 上优先 python3，Windows 上使用当前解释器，
#: 保证 "python" 语言开箱即用。
def default_python_command() -> str:
    if os.name == "nt":
        return f'"{sys.executable}"'
    return "python3"


#: 系统内置语言（首次启动写入 languages.json，之后可被动态注册覆盖/扩展）
def builtin_languages() -> dict:
    cpp_exe_ext = ".exe" if os.name == "nt" else ""
    return {
        "python": {
            "name": "python",
            "file_ext": ".py",
            "compile_cmd": None,
            "run_cmd": f"{default_python_command()} {{src}}",
            "time_limit": DEFAULT_TIME_LIMIT,
            "memory_limit": DEFAULT_MEMORY_LIMIT,
            # 解释型语言用 py_compile 做语法检查，语法错误按 CE 处理
            "check_cmd": f"{default_python_command()} -m py_compile {{src}}",
        },
        "cpp": {
            "name": "cpp",
            "file_ext": ".cpp",
            "compile_cmd": "g++ {src} -O2 -std=c++14 -o {exe}",
            "run_cmd": "{exe}",
            "time_limit": DEFAULT_TIME_LIMIT,
            "memory_limit": DEFAULT_MEMORY_LIMIT,
            "exe_ext": cpp_exe_ext,
        },
        "c": {
            "name": "c",
            "file_ext": ".c",
            "compile_cmd": "gcc {src} -O2 -std=c11 -o {exe}",
            "run_cmd": "{exe}",
            "time_limit": DEFAULT_TIME_LIMIT,
            "memory_limit": DEFAULT_MEMORY_LIMIT,
            "exe_ext": cpp_exe_ext,
        },
    }
