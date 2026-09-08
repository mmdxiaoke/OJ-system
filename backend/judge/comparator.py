"""输出比对。

按题目输入输出规范：忽略行末空格与末尾多余换行，其余必须严格一致。
"""
from __future__ import annotations


def normalize(text: str) -> str:
    if text is None:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def compare(actual: str, expected: str) -> bool:
    return normalize(actual) == normalize(expected)


def diff_preview(actual: str, expected: str, limit: int = 200) -> str:
    """给出简短差异提示，便于评测日志调试。"""
    got = normalize(actual)
    want = normalize(expected)
    if got == want:
        return ""
    got_lines = got.split("\n")
    want_lines = want.split("\n")
    for i, (a, b) in enumerate(zip(got_lines, want_lines, strict=False), start=1):
        if a != b:
            return f"line {i}: expected {b[:limit]!r}, got {a[:limit]!r}"
    if len(got_lines) > len(want_lines):
        return f"extra output from line {len(want_lines) + 1}: {got_lines[len(want_lines)][:limit]!r}"
    return f"missing output from line {len(got_lines) + 1}, expected {want_lines[len(got_lines)][:limit]!r}"
