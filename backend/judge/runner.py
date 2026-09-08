"""用户代码执行器：进程启动、资源限制、超时/超内存判定。

跨平台策略：
* 统一使用 ``psutil`` 轮询采样子进程（含其子进程）的 RSS 峰值，超过
  ``memory_limit`` 立即终止并判定 MLE；
* POSIX 额外设置 ``RLIMIT_CPU`` / ``RLIMIT_FSIZE`` 作为兜底；
* 超时后杀掉整棵进程树，避免用户代码派生的子进程残留；
* 不使用 shell，命令先切分成 argv 再 exec。
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field

from backend import config

try:  # 仅 POSIX 存在
    import resource  # type: ignore
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

IS_WINDOWS = os.name == "nt"


@dataclass
class RunResult:
    """一次程序运行的结果。"""

    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    time: float = 0.0
    memory: float = 0.0          # 峰值内存，单位 MB
    timed_out: bool = False
    memory_exceeded: bool = False
    output_truncated: bool = False
    internal_error: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def failed_to_start(self) -> bool:
        return bool(self.internal_error)


def _preexec(time_limit: float):  # pragma: no cover - 仅在 POSIX 生效
    if IS_WINDOWS:
        return None

    def _set_limits() -> None:
        os.setsid()
        try:
            import resource as _res

            cpu = max(1, int(time_limit) + 1)
            _res.setrlimit(_res.RLIMIT_CPU, (cpu, cpu + 1))
            _res.setrlimit(_res.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
            _res.setrlimit(_res.RLIMIT_CORE, (0, 0))
        except Exception:
            pass

    return _set_limits


async def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:  # pragma: no cover
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.kill()
    with contextlib.suppress(asyncio.TimeoutError, ProcessLookupError):
        await asyncio.wait_for(proc.wait(), timeout=5)


async def _read_limited(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, bool]:
    if stream is None:
        return b"", False
    buf = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if len(buf) < limit:
            room = limit - len(buf)
            buf.extend(chunk[:room])
            if room < len(chunk):
                truncated = True
        else:
            truncated = True
    return bytes(buf), truncated


def _tree_memory_mb(pid: int) -> float:
    if psutil is None:
        return 0.0
    try:
        proc = psutil.Process(pid)
        total = 0
        for child in [proc, *proc.children(recursive=True)]:
            try:
                total += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0.0


async def _memory_monitor(proc: asyncio.subprocess.Process, limit_mb: float, state: dict) -> None:
    """轮询采样内存，超过限制立即终止。"""
    if psutil is None:
        return
    interval = config.MEMORY_POLL_INTERVAL
    while True:
        if proc.returncode is not None:
            return
        usage = _tree_memory_mb(proc.pid)
        if usage > state["peak"]:
            state["peak"] = usage
        if limit_mb and usage > limit_mb:
            state["exceeded"] = True
            state["peak"] = usage
            await _kill_tree(proc)
            return
        await asyncio.sleep(interval)


async def run_program(
    argv: list[str],
    *,
    stdin_data: str = "",
    cwd: str | None = None,
    time_limit: float = config.DEFAULT_TIME_LIMIT,
    memory_limit_mb: float = config.DEFAULT_MEMORY_LIMIT,
    env: dict | None = None,
) -> RunResult:
    """运行一个程序并收集结果。"""
    result = RunResult()
    if not argv:
        result.internal_error = "empty command"
        return result

    run_env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "HOME": cwd or os.path.expanduser("~"),
        "TMPDIR": cwd or os.environ.get("TEMP", "/tmp"),
        "TEMP": cwd or os.environ.get("TEMP", "/tmp"),
        "TMP": cwd or os.environ.get("TEMP", "/tmp"),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "SystemDrive": os.environ.get("SYSTEMDRIVE", "C:"),
    }
    if env:
        run_env.update(env)

    popen_kwargs: dict = {}
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:  # pragma: no cover
        popen_kwargs["preexec_fn"] = _preexec(time_limit)

    started = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=run_env,
            **popen_kwargs,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        result.internal_error = f"failed to start program: {exc.__class__.__name__}"
        return result

    state = {"peak": 0.0, "exceeded": False}
    stdout_task = asyncio.create_task(_read_limited(proc.stdout, config.MAX_OUTPUT_BYTES))
    stderr_task = asyncio.create_task(_read_limited(proc.stderr, config.MAX_OUTPUT_BYTES))
    monitor_task = asyncio.create_task(_memory_monitor(proc, memory_limit_mb, state))

    if proc.stdin is not None:
        try:
            if stdin_data:
                proc.stdin.write(stdin_data.encode("utf-8", "replace"))
                await proc.stdin.drain()
            proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError, RuntimeError):
            pass

    try:
        await asyncio.wait_for(proc.wait(), timeout=time_limit)
    except asyncio.TimeoutError:
        result.timed_out = True
        await _kill_tree(proc)
    finally:
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task

    result.time = time.perf_counter() - started
    try:
        out, out_trunc = await asyncio.wait_for(stdout_task, timeout=5)
        err, err_trunc = await asyncio.wait_for(stderr_task, timeout=5)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        out, err, out_trunc, err_trunc = b"", b"", False, False
    result.stdout = out.decode("utf-8", "replace")
    result.stderr = err.decode("utf-8", "replace")
    result.output_truncated = out_trunc or err_trunc
    result.memory = round(state["peak"], 2)
    result.memory_exceeded = bool(state["exceeded"])
    result.exit_code = proc.returncode
    if result.timed_out:
        result.memory = round(max(state["peak"], _tree_memory_mb(proc.pid)), 2)
    return result


async def compile_program(
    argv: list[str],
    *,
    cwd: str,
    time_limit: float = config.COMPILE_TIME_LIMIT,
    env: dict | None = None,
) -> RunResult:
    """编译用户代码（不做内存限制，但限制编译时间）。"""
    return await run_program(
        argv,
        stdin_data="",
        cwd=cwd,
        time_limit=time_limit,
        memory_limit_mb=0,  # 0 表示不限制
        env=env,
    )
