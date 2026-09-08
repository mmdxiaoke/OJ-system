"""评测引擎：编译、逐测试点运行、结果汇总。"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

from backend import config
from backend.judge import comparator
from backend.judge.runner import RunResult, compile_program, run_program
from backend.services import language_service, problem_service

# 单条日志中保存的 stderr / 差异信息长度上限
MESSAGE_LIMIT = 800


def _truncate(text: str, limit: int = MESSAGE_LIMIT) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + " ... (truncated)"


def _build_argv(cmd: str, mapping: dict[str, str]) -> list[str]:
    argv = language_service.split_command(cmd)
    out = []
    for token in argv:
        for key, value in mapping.items():
            token = token.replace(key, value)
        out.append(token)
    return language_service.resolve_executable(out)


def _effective_limits(problem_raw: dict, language: dict) -> tuple[float, float]:
    """题目配置 -> 语言配置 -> 系统默认值。"""
    t = problem_raw.get("time_limit")
    if t is None:
        t = language.get("time_limit")
    if t is None:
        t = config.DEFAULT_TIME_LIMIT
    m = problem_raw.get("memory_limit")
    if m is None:
        m = language.get("memory_limit")
    if m is None:
        m = config.DEFAULT_MEMORY_LIMIT
    return float(t), float(m)


def _classify(result: RunResult, expected: str) -> tuple[str, str]:
    """把一次运行的结果映射为测试点状态。"""
    if result.timed_out:
        return "TLE", "time limit exceeded"
    if result.memory_exceeded:
        return "MLE", "memory limit exceeded"
    if result.failed_to_start:
        return "UNK", result.internal_error
    if result.exit_code != 0:
        detail = _truncate(result.stderr) or f"process exited with code {result.exit_code}"
        return "RE", detail
    if result.output_truncated:
        return "WA", "output too long"
    if not comparator.compare(result.stdout, expected):
        return "WA", comparator.diff_preview(result.stdout, expected)
    return "AC", ""


async def judge_submission(submission_id: str, submission: dict | None = None) -> dict:
    """执行一次完整评测，并写回评测结果。

    :param submission: 可选，避免重复读取。
    """
    from backend.services import submission_service  # 局部导入避免循环依赖

    if submission is None:
        submission = await submission_service.get_submission(submission_id)
    if submission is None:
        return {}

    language_name = submission.get("language", "")
    problem_id = submission.get("problem_id", "")
    code = submission.get("code", "")

    problem_raw = await problem_service.get_problem_raw(problem_id)
    language = await language_service.get_language(language_name)

    if problem_raw is None:
        return await submission_service.finish_submission(
            submission_id,
            status="error",
            error_info="problem not found",
            run_info={"result": "failed", "message": "problem not found"},
        )
    if language is None:
        return await submission_service.finish_submission(
            submission_id,
            status="error",
            error_info="language not found",
            run_info={"result": "failed", "message": "language not found"},
        )

    time_limit, memory_limit = _effective_limits(problem_raw, language)
    testcases = problem_raw.get("testcases") or []
    counts = config.SCORE_PER_TESTCASE * len(testcases)

    workdir = await asyncio.to_thread(tempfile.mkdtemp, None, "oj_run_")
    try:
        return await _judge_in_workdir(
            submission_id=submission_id,
            code=code,
            language=language,
            testcases=testcases,
            counts=counts,
            time_limit=time_limit,
            memory_limit=memory_limit,
            workdir=workdir,
        )
    except Exception as exc:
        return await submission_service.finish_submission(
            submission_id,
            status="error",
            error_info=f"internal judge error: {exc.__class__.__name__}",
            run_info={"result": "failed", "message": "judge crashed"},
        )
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)


async def _judge_in_workdir(
    *,
    submission_id: str,
    code: str,
    language: dict,
    testcases: list[dict],
    counts: int,
    time_limit: float,
    memory_limit: float,
    workdir: str,
) -> dict:
    from backend.services import submission_service

    file_ext = language.get("file_ext", ".txt")
    src_path = os.path.join(workdir, f"main{file_ext}")
    exe_path = os.path.join(workdir, "main" + (language.get("exe_ext") or ""))
    await asyncio.to_thread(_write_source, src_path, code)

    mapping = {"{src}": src_path, "{exe}": exe_path, "{workdir}": workdir}

    compile_info: dict | None = None
    compile_cmd = language.get("compile_cmd")
    check_cmd = language.get("check_cmd")

    if compile_cmd:
        argv = _build_argv(compile_cmd, mapping)
        cres = await compile_program(argv, cwd=workdir)
        if cres.failed_to_start:
            return await submission_service.finish_submission(
                submission_id,
                status="error",
                error_info=cres.internal_error,
                compile_info={"result": "failed", "message": cres.internal_error},
                run_info={"result": "failed", "message": "compiler not available"},
                counts=counts,
            )
        if cres.timed_out:
            msg = "compilation timed out"
            return await submission_service.finish_submission(
                submission_id,
                status="success",
                score=0,
                counts=counts,
                compile_info={"result": "failed", "message": msg},
                run_info={"result": "skipped", "message": "compilation failed"},
                details=[],
            )
        if cres.exit_code != 0:
            return await submission_service.finish_submission(
                submission_id,
                status="success",
                score=0,
                counts=counts,
                compile_info={"result": "failed", "message": _truncate(cres.stderr) or "compilation failed"},
                run_info={"result": "skipped", "message": "compilation failed"},
                details=[],
            )
        compile_info = {"result": "success", "message": ""}
    elif check_cmd:
        argv = _build_argv(check_cmd, mapping)
        cres = await compile_program(argv, cwd=workdir, time_limit=5.0)
        if cres.exit_code not in (0, None) and not cres.failed_to_start:
            return await submission_service.finish_submission(
                submission_id,
                status="success",
                score=0,
                counts=counts,
                compile_info={"result": "failed", "message": _truncate(cres.stderr) or "syntax error"},
                run_info={"result": "skipped", "message": "compilation failed"},
                details=[],
            )
        compile_info = None  # 解释型语言按 API 文档返回 null

    run_argv = _build_argv(language.get("run_cmd", "{src}"), mapping)
    details: list[dict] = []
    score = 0
    peak_time = 0.0
    peak_memory = 0.0
    first_failure = ""
    stopped_early = False

    for index, case in enumerate(testcases, start=1):
        if stopped_early:
            details.append({"id": index, "result": "UNK", "time": 0.0, "memory": 0.0,
                            "message": "skipped: previous test case crashed the judge"})
            continue
        result = await run_program(
            run_argv,
            stdin_data=case.get("input", ""),
            cwd=workdir,
            time_limit=time_limit,
            memory_limit_mb=memory_limit,
        )
        status, message = _classify(result, case.get("output", ""))
        if status == "UNK" and result.failed_to_start:
            stopped_early = True
        details.append({
            "id": index,
            "result": status,
            "time": round(result.time, 3),
            "memory": round(result.memory, 2),
            "message": message,
        })
        peak_time = max(peak_time, result.time)
        peak_memory = max(peak_memory, result.memory)
        if status == "AC":
            score += config.SCORE_PER_TESTCASE
        elif not first_failure:
            first_failure = f"test case {index}: {status} {message}".strip()

    if not testcases:
        run_info = {"result": "finished", "message": "no test cases configured"}
    else:
        run_info = {"result": "finished", "message": f"{len(testcases)} test cases finished"}

    return await submission_service.finish_submission(
        submission_id,
        status="success",
        score=score,
        counts=counts,
        compile_info=compile_info,
        run_info=run_info,
        error_info=first_failure if score < counts else "",
        details=details,
        time=round(peak_time, 3),
        memory=round(peak_memory, 2),
    )


def _write_source(path: str, code: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(code or "")


async def judge_submission_task(submission_id: str) -> None:
    """后台任务入口：保证异常不会逃逸。"""
    try:
        await judge_submission(submission_id)
    except Exception:
        from backend.services import submission_service

        await submission_service.finish_submission(
            submission_id,
            status="error",
            error_info="internal judge error",
            run_info={"result": "failed", "message": "judge crashed"},
        )
