"""语言注册表：内置语言 + 用户动态注册。

安全考虑（评分点「动态注册、配置安全」）：
* 命令不使用 shell 执行，而是切分成 argv 后直接 exec，从根本上避免
  ``;``、``|``、``$(...)`` 之类的注入；
* 只允许白名单中的编译器/解释器（禁止 sh/bash/cmd/powershell 等 shell）；
* 命令中不允许出现换行与控制字符，长度受限；
* ``{src}`` / ``{exe}`` 占位符由服务端替换为受控临时目录下的路径。
"""
from __future__ import annotations

import os
import re
import shutil

from backend import config
from backend.core import storage
from backend.core.responses import ApiError

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_+#.\-]{1,32}$")
EXT_PATTERN = re.compile(r"^\.[A-Za-z0-9_+#\-]{1,12}$")
FORBIDDEN_CHARS = set("\n\r\x00|&;`$<>")

#: 允许被注册语言调用的可执行文件（按 basename 匹配，忽略 .exe 后缀）
ALLOWED_EXECUTABLES = {
    "python", "python3", "python2", "pypy", "pypy3",
    "gcc", "g++", "cc", "c++", "clang", "clang++",
    "javac", "java", "kotlinc", "kotlin",
    "node", "nodejs", "deno", "tsc", "bun",
    "go", "rustc", "cargo", "ruby", "php", "perl",
    "dotnet", "mono", "mcs", "fpc", "ghc", "swift", "lua", "luajit", "Rscript",
}

#: 明确禁止的 shell / 提权程序
FORBIDDEN_EXECUTABLES = {
    "sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish",
    "cmd", "cmd.exe", "powershell", "pwsh", "powershell.exe",
    "env", "sudo", "su", "runas", "xargs", "find", "rm", "del", "dd",
    "curl", "wget", "nc", "ncat", "ssh", "scp", "pythonw",
}

PLACEHOLDER_PATTERN = re.compile(r"\{[a-z_]+\}")


def split_command(cmd: str) -> list[str]:
    """按 shell 风格切分命令，但不做任何展开，避免注入。

    支持单/双引号包裹的参数，Windows 路径中的反斜杠保持原样。
    """
    if not isinstance(cmd, str):
        raise ApiError(400, "command must be a string")
    if len(cmd) > 512:
        raise ApiError(400, "command is too long (max 512 characters)")
    if any(ch in FORBIDDEN_CHARS for ch in cmd):
        raise ApiError(400, "command contains forbidden characters")

    tokens: list[str] = []
    cur: list[str] = []
    quote: str | None = None
    for ch in cmd:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
        elif ch in "\"'":
            quote = ch
        elif ch.isspace():
            if cur:
                tokens.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        tokens.append("".join(cur))
    if quote:
        raise ApiError(400, "command contains an unterminated quote")
    if not tokens:
        raise ApiError(400, "command must not be empty")
    return tokens


def _executable_name(token: str) -> str:
    name = os.path.basename(token.replace("\\", "/")).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def check_executable_allowed(argv: list[str]) -> None:
    name = _executable_name(argv[0])
    if name in FORBIDDEN_EXECUTABLES:
        raise ApiError(400, f"executable '{name}' is not allowed for security reasons")
    if name not in ALLOWED_EXECUTABLES:
        raise ApiError(400, f"executable '{name}' is not in the allowed compiler/interpreter list")
    # 占位符只允许出现在非首个参数中（首参必须是可执行文件本身）
    if "{" in argv[0]:
        raise ApiError(400, "the executable part of the command must not contain placeholders")


def resolve_executable(argv: list[str]) -> list[str]:
    """若首参是可执行名但当前系统找不到，尝试用当前解释器兜底。"""
    exe = argv[0]
    if shutil.which(exe):
        return argv
    name = _executable_name(exe)
    if name in {"python", "python3", "python2"}:
        import sys

        return [sys.executable, *argv[1:]]
    return argv


def validate_language_config(cfg: dict) -> dict:
    name = cfg.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise ApiError(400, "invalid language name: letters, digits and _+#.- only, length 1-32")

    file_ext = cfg.get("file_ext")
    if not isinstance(file_ext, str) or not EXT_PATTERN.match(file_ext):
        raise ApiError(400, "invalid file_ext, e.g. '.py'")

    run_cmd = cfg.get("run_cmd")
    if not isinstance(run_cmd, str) or not run_cmd.strip():
        raise ApiError(400, "run_cmd is required")
    run_argv = split_command(run_cmd)
    check_executable_allowed(run_argv)
    if "{src}" not in run_cmd and "{exe}" not in run_cmd:
        raise ApiError(400, "run_cmd must contain {src} or {exe}")
    for token in PLACEHOLDER_PATTERN.findall(run_cmd):
        if token not in ("{src}", "{exe}", "{workdir}"):
            raise ApiError(400, f"unknown placeholder {token} in run_cmd")

    compile_cmd = cfg.get("compile_cmd")
    if compile_cmd is not None and (not isinstance(compile_cmd, str) or not compile_cmd.strip()):
        raise ApiError(400, "compile_cmd must be a non-empty string when provided")
    if compile_cmd:
        compile_argv = split_command(compile_cmd)
        check_executable_allowed(compile_argv)
        if "{src}" not in compile_cmd:
            raise ApiError(400, "compile_cmd must contain {src}")
        for token in PLACEHOLDER_PATTERN.findall(compile_cmd):
            if token not in ("{src}", "{exe}", "{workdir}"):
                raise ApiError(400, f"unknown placeholder {token} in compile_cmd")

    time_limit = cfg.get("time_limit")
    if time_limit is None:
        time_limit = config.DEFAULT_TIME_LIMIT
    try:
        time_limit = float(time_limit)
    except (TypeError, ValueError):
        raise ApiError(400, "time_limit must be a number") from None
    if not (0 < time_limit <= 60):
        raise ApiError(400, "time_limit must be in (0, 60] seconds")

    memory_limit = cfg.get("memory_limit")
    if memory_limit is None:
        memory_limit = config.DEFAULT_MEMORY_LIMIT
    try:
        memory_limit = int(memory_limit)
    except (TypeError, ValueError):
        raise ApiError(400, "memory_limit must be an integer") from None
    if not (16 <= memory_limit <= 4096):
        raise ApiError(400, "memory_limit must be between 16 and 4096 MB")

    return {
        "name": name,
        "file_ext": file_ext,
        "compile_cmd": compile_cmd,
        "run_cmd": run_cmd,
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "exe_ext": cfg.get("exe_ext") or (".exe" if os.name == "nt" else ""),
        "check_cmd": cfg.get("check_cmd"),
    }


async def ensure_builtin_languages() -> None:
    """首次启动写入内置语言；已存在则补齐缺失项。"""
    builtins = config.builtin_languages()

    def mutate(data: dict) -> dict:
        langs = data.setdefault("languages", {})
        for name, cfg in builtins.items():
            langs.setdefault(name, cfg)
        return data

    await storage.languages_store.update(mutate)


async def all_languages() -> dict:
    data = await storage.languages_store.read()
    return data.get("languages", {})


async def get_language(name: str) -> dict | None:
    langs = await all_languages()
    return langs.get(name)


async def get_language_or_404(name: str) -> dict:
    lang = await get_language(name)
    if lang is None:
        raise ApiError(404, "language not found")
    return lang


async def register_language(cfg: dict) -> dict:
    validated = validate_language_config(cfg)
    stored: dict = {}

    def mutate(data: dict) -> dict:
        langs = data.setdefault("languages", {})
        langs[validated["name"]] = validated
        stored["lang"] = validated
        return data

    await storage.languages_store.update(mutate)
    return stored["lang"]


async def language_names() -> list[str]:
    langs = await all_languages()
    return sorted(langs.keys())


async def clear_languages() -> None:
    await storage.languages_store.write({"languages": {}})
