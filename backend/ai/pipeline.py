"""AI 智能命题流水线（Advance）。

设计思路（对应评分点「题目合理性」「测试用例有效性」）：

1. **需求分析**：把知识点、难度、附加要求整理成结构化的命题纲要；
2. **题面生成**：产出可直接入库的题目字段（含样例、约束、提示）；
3. **参考程序 + 暴力程序**：让模型同时给出高效标程与朴素暴力解；
4. **数据生成脚本**：模型编写 Python 脚本，打印若干组输入（含小数据与极限数据）；
5. **实际执行与校验**：真正运行生成脚本得到输入，用标程产出期望输出，
   并在小数据上与暴力解交叉验证；不一致时回到第 3 步重试；
6. **整理结果**：输出可直接用于题目新增/编辑的完整配置。

所有中间产物都会通过进度事件实时推送，任务可被真正中断（取消 asyncio 任务 +
取消进行中的 HTTP 请求）。
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.ai.llm_client import LLMClient, extract_json
from backend.judge.runner import run_program

SYSTEM_BASE = (
    "你是一位资深的程序设计课程助教，负责为大学程序设计与算法课程命制 OJ 题目。"
    "你必须严格按照要求输出 JSON，不要输出任何多余的解释文字。"
)

STAGES = [
    ("analyze", "解析命题需求"),
    ("statement", "设计题面与约束"),
    ("solution", "编写参考程序与暴力程序"),
    ("generator", "生成测试数据"),
    ("verify", "校验测试数据与参考程序"),
    ("finalize", "整理题目配置"),
]


@dataclass
class TaskContext:
    task_id: str
    requirement: str
    problem_id: str | None = None
    difficulty: str | None = None
    knowledge_points: list[str] = field(default_factory=list)
    case_count: int = 12
    language: str = "python"
    emit: Callable[[dict], None] = lambda event: None
    add_usage: Callable[[int, int, bool], None] = lambda i, o, u: None
    existing_problem: dict | None = None
    artifacts: dict = field(default_factory=dict)


def _stage_prompt(stage: str, extra: str = "") -> str:
    """用统一的 STAGE 标记开头，便于服务端/测试桩识别阶段。"""
    return f"[STAGE:{stage}] {SYSTEM_BASE} {extra}"


async def _call_model(
    ctx: TaskContext,
    client: LLMClient,
    stage: str,
    user_prompt: str,
    *,
    extra_system: str = "",
    temperature: float = 0.3,
    live: bool = True,
) -> dict:
    ctx.emit({"type": "progress", "stage": stage, "message": f"正在{_stage_title(stage)}"})
    buffer: list[str] = []
    last_emit = 0.0

    def on_delta(piece: str) -> None:
        """流式回调：按时间节流推送增量文本，避免事件过多。"""
        nonlocal last_emit
        buffer.append(piece)
        now = time.monotonic()
        if live and now - last_emit >= 0.2:
            last_emit = now
            ctx.emit({"type": "delta", "stage": stage, "text": "".join(buffer[-8:])[-200:]})

    response = await client.chat(
        [
            {"role": "system", "content": _stage_prompt(stage, extra_system)},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        on_delta=on_delta,
    )
    ctx.add_usage(response.input_tokens, response.output_tokens, response.usage_available)
    if response.usage_available:
        ctx.emit({
            "type": "usage",
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        })
    ctx.artifacts.setdefault("raw_outputs", {})[stage] = response.content[:4000]
    return extract_json(response.content)


def _stage_title(stage: str) -> str:
    for name, title in STAGES:
        if name == stage:
            return title
    return stage


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _existing_context(ctx: TaskContext) -> str:
    if not ctx.existing_problem:
        return "本次命题没有参考题目，请从零设计。"
    problem = ctx.existing_problem
    return (
        "本次命题需要参考/改编以下已有题目，请保持其核心考查目标，并按新的需求调整：\n"
        + _dump({
            "id": problem.get("id"),
            "title": problem.get("title"),
            "description": problem.get("description"),
            "input_description": problem.get("input_description"),
            "output_description": problem.get("output_description"),
            "constraints": problem.get("constraints"),
            "samples": problem.get("samples", [])[:3],
            "tags": problem.get("tags", []),
            "difficulty": problem.get("difficulty", ""),
        })
    )


async def run_pipeline(ctx: TaskContext, client: LLMClient) -> dict:
    """执行完整命题流水线，返回可入库的题目配置与中间产物。"""
    # ---------------- 1. 需求分析 ----------------
    analysis = await _call_model(
        ctx,
        client,
        "analyze",
        (
            f"命题需求：{ctx.requirement}\n"
            f"期望难度：{ctx.difficulty or '不限'}\n"
            f"必须覆盖的知识点：{ctx.knowledge_points or ['由你根据需求判断']}\n"
            f"{_existing_context(ctx)}\n\n"
            "请输出 JSON：{\"knowledge_points\": [\"...\"], \"difficulty\": \"入门|普及-|普及/提高-|提高+\", "
            "\"core_algorithm\": \"...\", \"io_style\": \"标准输入输出\", \"data_scale\": \"数据规模描述\", "
            "\"edge_cases\": [\"需要覆盖的边界情况\"], \"test_dimensions\": [\"测试维度，如 随机/极端/退化\"]}"
        ),
    )

    # ---------------- 2. 题面 ----------------
    statement = await _call_model(
        ctx,
        client,
        "statement",
        (
            f"命题需求：{ctx.requirement}\n"
            f"命题纲要：{_dump(analysis)}\n"
            f"题目编号：{ctx.problem_id or '由你生成一个简短的英文 id（字母数字下划线）'}\n\n"
            "请输出完整题面 JSON，字段与 OJ 题目配置一致：\n"
            "{\"id\": \"...\", \"title\": \"...\", \"description\": \"...\", \"input_description\": \"...\", "
            "\"output_description\": \"...\", \"samples\": [{\"input\": \"...\", \"output\": \"...\"}], "
            "\"constraints\": \"...\", \"hint\": \"...\", \"source\": \"...\", \"tags\": [\"...\"], "
            "\"time_limit\": 1.0, \"memory_limit\": 128, \"author\": \"AI\", \"difficulty\": \"...\"}\n"
            "要求：题面用中文，严格使用标准输入输出，样例不少于 1 组且必须自洽。"
        ),
        temperature=0.5,
    )

    problem_id = ctx.problem_id or str(statement.get("id") or f"ai_{ctx.task_id[-6:]}")

    # ---------------- 3~5. 方案 + 数据 + 校验（最多两轮） ----------------
    reference_code = ""
    brute_code = ""
    generator_code = ""
    verification: dict = {}
    testcases: list[dict] = []
    last_error = ""

    for attempt in range(1, 3):
        solution = await _call_model(
            ctx,
            client,
            "solution",
            (
                f"题目配置：{_dump(statement)}\n"
                f"命题纲要：{_dump(analysis)}\n"
                f"{('上一轮校验失败信息：' + last_error) if last_error else ''}\n\n"
                "请输出 JSON：{\"reference_code\": \"Python3 标准输入输出标程，必须是高效正确解\", "
                "\"brute_code\": \"Python3 朴素暴力解，仅需在小数据上正确\", \"explanation\": \"算法说明\"}"
            ),
            temperature=0.2,
        )
        reference_code = str(solution.get("reference_code") or "")
        brute_code = str(solution.get("brute_code") or "")

        generator = await _call_model(
            ctx,
            client,
            "generator",
            (
                f"题目配置：{_dump(statement)}\n"
                f"命题纲要：{_dump(analysis)}\n"
                f"需要生成的测试点数量：{ctx.case_count}\n\n"
                "请编写一个 Python3 脚本，向标准输出打印一个 JSON 数组，每个元素形如 "
                "{\"input\": \"该测试点的完整标准输入\", \"scale\": \"small\" 或 \"large\", \"note\": \"该测试点想考察什么\"}。\n"
                f"要求：至少 3 个 small 规模的测试点用于暴力解交叉验证；覆盖 {_dump(analysis.get('edge_cases'))} 中的边界情况；"
                "包含 1~2 个数据规模达到题目约束上限的 large 测试点；输入必须严格符合题目的输入格式。\n"
                "请输出 JSON：{\"generator_code\": \"完整的 Python3 脚本源码\", \"case_plan\": [\"每个测试点的说明\"]}"
            ),
            temperature=0.2,
        )
        generator_code = str(generator.get("generator_code") or "")

        verification, testcases, last_error = await _verify_data(
            ctx, statement, reference_code, brute_code, generator_code
        )
        if verification.get("passed"):
            break
        ctx.emit({"type": "progress", "stage": "verify",
                  "message": f"第 {attempt} 轮校验未通过，正在根据反馈修正：{last_error[:120]}"})

    # ---------------- 6. 整理结果 ----------------
    ctx.emit({"type": "progress", "stage": "finalize", "message": "正在整理题目配置"})
    problem = {
        "id": problem_id,
        "title": str(statement.get("title") or f"AI 题目 {problem_id}"),
        "description": str(statement.get("description") or ""),
        "input_description": str(statement.get("input_description") or ""),
        "output_description": str(statement.get("output_description") or ""),
        "samples": _normalize_cases(statement.get("samples")) or [{"input": "", "output": ""}],
        "constraints": str(statement.get("constraints") or ""),
        "testcases": testcases,
        "hint": str(statement.get("hint") or ""),
        "source": str(statement.get("source") or "AI 智能命题"),
        "tags": [str(t) for t in (statement.get("tags") or [])][:10],
        "time_limit": float(statement.get("time_limit") or 1.0),
        "memory_limit": int(statement.get("memory_limit") or 128),
        "author": str(statement.get("author") or "AI"),
        "difficulty": str(statement.get("difficulty") or analysis.get("difficulty") or ""),
        "public_cases": False,
    }

    return {
        "problem": problem,
        "analysis": analysis,
        "reference_code": reference_code,
        "brute_code": brute_code,
        "generator_code": generator_code,
        "verification": verification,
        "usage_note": (
            "Token 用量来自模型接口返回的 usage 字段（含输入/输出 Token）；"
            "若服务端未返回 usage，则按字符数估算并在界面中标注。"
        ),
    }


def _normalize_cases(raw) -> list[dict]:
    out = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.append({"input": str(item.get("input", "")), "output": str(item.get("output", ""))})
    return out


async def _verify_data(
    ctx: TaskContext,
    statement: dict,
    reference_code: str,
    brute_code: str,
    generator_code: str,
) -> tuple[dict, list[dict], str]:
    """执行生成脚本，用标程产出期望输出，并用暴力解交叉验证小数据。"""
    ctx.emit({"type": "progress", "stage": "verify", "message": "正在运行数据生成脚本并校验"})
    if not reference_code.strip():
        return {"passed": False, "error": "参考程序为空"}, [], "参考程序为空"
    if not generator_code.strip():
        return {"passed": False, "error": "数据生成脚本为空"}, [], "数据生成脚本为空"

    workdir = await asyncio.to_thread(tempfile.mkdtemp, None, "oj_ai_")
    try:
        gen_path = os.path.join(workdir, "generator.py")
        ref_path = os.path.join(workdir, "reference.py")
        brute_path = os.path.join(workdir, "brute.py")
        await asyncio.to_thread(_write, gen_path, generator_code)
        await asyncio.to_thread(_write, ref_path, reference_code)
        if brute_code.strip():
            await asyncio.to_thread(_write, brute_path, brute_code)

        gen = await run_program(
            [sys.executable, gen_path], cwd=workdir, time_limit=20.0, memory_limit_mb=512
        )
        if gen.exit_code != 0 or not gen.stdout.strip():
            error = (gen.stderr or "生成脚本没有输出").strip()[:400]
            return {"passed": False, "error": f"数据生成脚本执行失败：{error}"}, [], error

        try:
            raw_cases = json.loads(gen.stdout[gen.stdout.find("["):])
        except (json.JSONDecodeError, ValueError) as exc:
            return {"passed": False, "error": f"生成脚本输出不是合法 JSON：{exc}"}, [], str(exc)

        cases = [c for c in raw_cases if isinstance(c, dict) and isinstance(c.get("input"), str)]
        if not cases:
            return {"passed": False, "error": "生成脚本没有产出任何测试点"}, [], "no cases"

        testcases: list[dict] = []
        mismatches: list[str] = []
        time_limit = float(statement.get("time_limit") or 1.0)
        memory_limit = float(statement.get("memory_limit") or 128)

        for index, case in enumerate(cases, start=1):
            if ctx.emit:
                ctx.emit({"type": "progress", "stage": "verify",
                          "message": f"正在生成第 {index}/{len(cases)} 个测试点的期望输出"})
            result = await run_program(
                [sys.executable, ref_path],
                stdin_data=case["input"],
                cwd=workdir,
                time_limit=max(2.0, time_limit * 3),
                memory_limit_mb=max(256.0, memory_limit * 2),
            )
            if result.exit_code != 0:
                mismatches.append(f"第 {index} 个测试点：标程运行失败（{result.stderr.strip()[:120]}）")
                continue
            expected = result.stdout
            testcases.append({"input": case["input"], "output": expected})

            # 小数据上用暴力解交叉验证，防止标程本身写错
            if case.get("scale") == "small" and brute_code.strip():
                brute = await run_program(
                    [sys.executable, brute_path],
                    stdin_data=case["input"],
                    cwd=workdir,
                    time_limit=10.0,
                    memory_limit_mb=512,
                )
                if brute.exit_code != 0:
                    mismatches.append(f"第 {index} 个测试点：暴力解运行失败")
                elif brute.stdout.strip() != expected.strip():
                    mismatches.append(
                        f"第 {index} 个测试点：标程与暴力解结果不一致"
                        f"（标程 {expected.strip()[:40]!r} / 暴力 {brute.stdout.strip()[:40]!r}）"
                    )

        summary = {
            "passed": not mismatches and bool(testcases),
            "case_count": len(testcases),
            "small_cases": sum(1 for c in cases if c.get("scale") == "small"),
            "large_cases": sum(1 for c in cases if c.get("scale") == "large"),
            "mismatches": mismatches[:5],
            "case_plan": [c.get("note", "") for c in cases][:20],
        }
        if mismatches:
            summary["error"] = "; ".join(mismatches[:3])
            return summary, testcases, summary["error"]
        if not testcases:
            summary["error"] = "没有任何测试点通过校验"
            return summary, [], summary["error"]
        return summary, testcases, ""
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)


def _write(path: str, code: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(code)
