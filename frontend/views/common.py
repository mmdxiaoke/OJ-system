"""页面公共工具：会话状态、数据缓存、选择器与统一提示。

这里集中了「减少手输 ID」的辅助函数：题目选择器、提交选择器、分页控件等，
各页面直接调用即可，保证交互风格一致。
"""
from __future__ import annotations

import json

import streamlit as st

from frontend.api_client import ApiResult, OJClient

DEFAULT_BASE = "http://127.0.0.1:8000"

# 状态与结果的统一展示文案
STATUS_LABEL = {"pending": "⏳ 评测中", "success": "✅ 已完成", "error": "❌ 评测出错"}
RESULT_LABEL = {
    "AC": "✅ AC",
    "WA": "❌ WA",
    "TLE": "⏰ TLE",
    "MLE": "💾 MLE",
    "RE": "💥 RE",
    "CE": "🛠️ CE",
    "UNK": "❓ UNK",
}
ROLE_LABEL = {"user": "普通用户", "admin": "管理员", "banned": "已禁用"}

# 提交页的代码模板（按语言插入）
CODE_TEMPLATES = {
    "python": (
        "import sys\n\n\n"
        "def main() -> None:\n"
        "    data = sys.stdin.read().split()\n"
        "    if not data:\n"
        "        return\n"
        "    # TODO: 在这里编写你的逻辑\n"
        "    print(data)\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    ),
    "cpp": (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    ios::sync_with_stdio(false);\n"
        "    cin.tie(nullptr);\n\n"
        "    // TODO: 在这里编写你的逻辑\n\n"
        "    return 0;\n"
        "}\n"
    ),
    "c": (
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        "    /* TODO: 在这里编写你的逻辑 */\n"
        "    return 0;\n"
        "}\n"
    ),
    "java": (
        "import java.util.*;\n\n"
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        Scanner sc = new Scanner(System.in);\n"
        "        // TODO: 在这里编写你的逻辑\n"
        "    }\n"
        "}\n"
    ),
}


# ---------------------------------------------------------------------------
# 会话与身份
# ---------------------------------------------------------------------------
def client() -> OJClient:
    if "client" not in st.session_state:
        st.session_state.client = OJClient(st.session_state.get("api_base", DEFAULT_BASE))
    return st.session_state.client


def rebuild_client(base_url: str) -> None:
    st.session_state.client = OJClient(base_url)
    st.session_state.user = None
    clear_cache()


def current_user() -> dict | None:
    return st.session_state.get("user")


def is_admin() -> bool:
    user = current_user()
    return bool(user) and user.get("role") == "admin"


def require_login() -> dict:
    user = current_user()
    if not user:
        st.warning("请先登录后再使用该功能。")
        st.stop()
    return user


def require_admin() -> dict:
    user = require_login()
    if user.get("role") != "admin":
        st.error("该页面仅管理员可用（403）。")
        st.stop()
    return user


# ---------------------------------------------------------------------------
# 提示
# ---------------------------------------------------------------------------
def notify(result: ApiResult, success_msg: str | None = None) -> bool:
    """根据响应展示成功/失败信息，返回是否成功。"""
    if result.ok:
        st.success(success_msg or result.msg or "操作成功")
        return True
    st.error(result.error_text())
    return False


def show_data(result: ApiResult, success_msg: str | None = None) -> bool:
    """成功时提示并返回 data，失败时展示错误。"""
    if result.ok:
        if success_msg:
            st.success(success_msg)
        return True
    st.error(result.error_text())
    return False


def field_row(label: str, value) -> None:
    st.markdown(f"**{label}**：{value if value not in (None, '') else '—'}")


def status_text(status: str | None) -> str:
    return STATUS_LABEL.get(status or "", status or "—")


def result_text(result: str | None) -> str:
    return RESULT_LABEL.get(result or "", result or "—")


def role_text(role: str | None) -> str:
    return ROLE_LABEL.get(role or "", role or "—")


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
def clear_cache() -> None:
    for key in ("_problems_cache", "_submissions_cache", "_me_cache", "_languages_cache"):
        st.session_state.pop(key, None)


def refresh(force: bool = True) -> None:
    """清缓存并重新运行脚本（按钮回调里使用）。"""
    if force:
        clear_cache()
    st.rerun()


# ---------------------------------------------------------------------------
# 题目
# ---------------------------------------------------------------------------
def problem_list(force: bool = False) -> list[dict]:
    """带缓存的题目列表（失败时返回空列表并记录错误）。"""
    if force or "_problems_cache" not in st.session_state:
        result = client().list_problems()
        if result.ok:
            st.session_state["_problems_cache"] = result.data or []
            st.session_state.pop("_problems_error", None)
        else:
            st.session_state["_problems_cache"] = []
            st.session_state["_problems_error"] = result.error_text()
    return st.session_state.get("_problems_cache", [])


def problem_title(problem_id: str | None) -> str:
    if not problem_id:
        return "—"
    for item in problem_list():
        if item.get("id") == problem_id:
            return item.get("title") or problem_id
    return problem_id


def problem_label(problem: dict) -> str:
    title = problem.get("title") or "（无标题）"
    return f"{problem.get('id')} · {title}"


def _ensure_option(key: str, options: list) -> None:
    """保证 selectbox 的 session_state 值与当前选项一致，避免切换数据后报错。"""
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def problem_selector(
    label: str = "选择题目",
    key: str = "problem_pick",
    *,
    allow_empty: bool = False,
    empty_label: str = "（不指定）",
    show_refresh: bool = True,
) -> str | None:
    """题目下拉选择器，返回 problem_id（未选择时返回 None）。"""
    problems = problem_list()
    head, tail = st.columns([5, 1]) if show_refresh else (st.container(), None)
    with head:
        if not problems:
            st.info("题库为空：可在「新增题目」创建，或使用「AI 智能命题」生成题目。")
            return None
        options = [p["id"] for p in problems]
        if allow_empty:
            options = ["", *options]
        _ensure_option(key, options)
        labels = {p["id"]: problem_label(p) for p in problems}
        chosen = st.selectbox(
            label, options, key=key,
            format_func=lambda value: empty_label if value == "" else labels.get(value, value),
        )
    if tail is not None and tail.button("🔄", key=f"{key}_refresh", help="刷新题目列表"):
        refresh()
    return chosen or None


# ---------------------------------------------------------------------------
# 提交
# ---------------------------------------------------------------------------
def my_recent_submissions(limit: int = 30, force: bool = False) -> list[dict]:
    """当前用户最近的提交记录（用于下拉选择）。"""
    user = current_user()
    if not user:
        return []
    if force or "_submissions_cache" not in st.session_state:
        result = client().list_submissions(user_id=user["user_id"], page_size=limit)
        st.session_state["_submissions_cache"] = (result.data or {}).get("submissions", []) if result.ok else []
    return st.session_state.get("_submissions_cache", [])


def submission_label(item: dict) -> str:
    status = status_text(item.get("status"))
    if item.get("status") == "success":
        score = f"{item.get('score')}/{item.get('counts')}"
    else:
        score = ""
    return f"#{item.get('submission_id')} · {item.get('problem_id')} · {status} {score}".strip()


def submission_selector(
    label: str = "选择提交记录",
    key: str = "submission_pick",
    *,
    limit: int = 30,
    allow_manual: bool = True,
) -> str | None:
    """从「我的最近提交」里选择 submission_id，也允许手动输入。"""
    items = my_recent_submissions(limit=limit)
    head, tail = st.columns([5, 1])
    with head:
        if items:
            options = [str(item["submission_id"]) for item in items]
            _ensure_option(key, options)
            labels = {str(i["submission_id"]): submission_label(i) for i in items}
            chosen = st.selectbox(
                label, options, key=key, format_func=lambda v: labels.get(v, v),
            )
        else:
            st.info("暂无提交记录，先到「提交代码」页面提交一次吧。")
            chosen = None
    if tail.button("🔄", key=f"{key}_refresh", help="刷新提交列表"):
        refresh()
    if allow_manual:
        manual = st.text_input("或手动输入 submission_id", key=f"{key}_manual")
        if manual.strip():
            return manual.strip()
    return str(chosen) if chosen else None


# ---------------------------------------------------------------------------
# 分页
# ---------------------------------------------------------------------------
def pager(total: int, page: int, page_size: int, key: str) -> int:
    """渲染「上一页 / 下一页」控件，返回当前页码。"""
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, page), total_pages)
    col1, col2, col3 = st.columns([1, 3, 1])
    if col1.button("← 上一页", key=f"{key}_prev", disabled=page <= 1):
        st.session_state[f"{key}_page"] = page - 1
        st.rerun()
    col2.markdown(
        f"<div style='text-align:center'>第 <b>{page}</b> / {total_pages} 页 · 共 <b>{total}</b> 条</div>",
        unsafe_allow_html=True,
    )
    if col3.button("下一页 →", key=f"{key}_next", disabled=page >= total_pages):
        st.session_state[f"{key}_page"] = page + 1
        st.rerun()
    return page


# ---------------------------------------------------------------------------
# 题目配置编辑器
# ---------------------------------------------------------------------------
def cases_editor(title: str, key: str, cases: list[dict], *, default_count: int = 1) -> list[dict]:
    """样例 / 测试点的图形化编辑器：先选数量，再逐条填写输入输出。"""
    st.markdown(f"**{title}**")
    initial = list(cases) if cases else []
    count = st.number_input(
        "数量", min_value=0, max_value=30,
        value=max(len(initial), default_count), step=1, key=f"{key}_count",
    )
    rows: list[dict] = []
    for index in range(int(count)):
        existing = initial[index] if index < len(initial) else {"input": "", "output": ""}
        with st.expander(f"{title} #{index + 1}", expanded=index < 2):
            col1, col2 = st.columns(2)
            rows.append({
                "input": col1.text_area("输入", value=existing.get("input", ""),
                                        key=f"{key}_{index}_in", height=110),
                "output": col2.text_area("输出", value=existing.get("output", ""),
                                         key=f"{key}_{index}_out", height=110),
            })
    return rows


DIFFICULTY_OPTIONS = ["", "入门", "普及-", "普及/提高-", "提高+/省选-", "省选/NOI-", "NOI/NOI+"]


def problem_form(problem: dict, key_prefix: str) -> dict | None:
    """图形化编辑题目配置，返回可直接提交的 dict（校验失败返回 None）。"""
    col1, col2 = st.columns([3, 1])
    problem_id = col1.text_input("题目 ID（字母/数字/下划线/连字符）", value=problem.get("id", ""),
                                 key=f"{key_prefix}_id")
    current_difficulty = problem.get("difficulty", "")
    difficulty = col2.selectbox(
        "难度", DIFFICULTY_OPTIONS,
        index=DIFFICULTY_OPTIONS.index(current_difficulty) if current_difficulty in DIFFICULTY_OPTIONS else 0,
        key=f"{key_prefix}_difficulty",
    )
    title = st.text_input("题目标题", value=problem.get("title", ""), key=f"{key_prefix}_title")
    description = st.text_area("题目描述", value=problem.get("description", ""),
                               key=f"{key_prefix}_desc", height=140)
    col1, col2 = st.columns(2)
    input_desc = col1.text_area("输入格式", value=problem.get("input_description", ""),
                                key=f"{key_prefix}_in_desc", height=110)
    output_desc = col2.text_area("输出格式", value=problem.get("output_description", ""),
                                 key=f"{key_prefix}_out_desc", height=110)
    constraints = st.text_input("数据范围与限制", value=problem.get("constraints", ""),
                                key=f"{key_prefix}_constraints")
    col1, col2, col3 = st.columns(3)
    time_limit = col1.number_input("时间限制（秒）", min_value=0.1, max_value=60.0, step=0.5,
                                   value=float(problem.get("time_limit") or 3.0), key=f"{key_prefix}_tl")
    memory_limit = col2.number_input("内存限制（MB）", min_value=16, max_value=4096, step=16,
                                     value=int(problem.get("memory_limit") or 128), key=f"{key_prefix}_ml")
    author = col3.text_input("作者", value=problem.get("author", ""), key=f"{key_prefix}_author")
    col1, col2 = st.columns(2)
    source = col1.text_input("题目来源", value=problem.get("source", ""), key=f"{key_prefix}_source")
    tags = col2.text_input("标签（用逗号分隔）", value=", ".join(problem.get("tags") or []),
                           key=f"{key_prefix}_tags")
    hint = st.text_input("提示（可选）", value=problem.get("hint", ""), key=f"{key_prefix}_hint")

    samples = cases_editor("样例", f"{key_prefix}_sample", problem.get("samples") or [], default_count=1)
    testcases = cases_editor("测试点（评测使用）", f"{key_prefix}_case", problem.get("testcases") or [],
                             default_count=1)

    payload = {
        "id": problem_id.strip(),
        "title": title.strip(),
        "description": description,
        "input_description": input_desc,
        "output_description": output_desc,
        "samples": samples,
        "constraints": constraints.strip(),
        "testcases": testcases,
        "hint": hint.strip(),
        "source": source.strip(),
        "tags": [t.strip() for t in tags.replace("，", ",").split(",") if t.strip()],
        "time_limit": float(time_limit),
        "memory_limit": int(memory_limit),
        "author": author.strip(),
        "difficulty": difficulty,
    }
    with st.expander("预览提交的 JSON"):
        st.json(payload)
    if not problem_id.strip():
        st.error("题目 ID 不能为空（400）。")
        return None
    if not title.strip() or not description.strip() or not input_desc.strip() or not output_desc.strip():
        st.error("标题、描述、输入格式、输出格式都不能为空（400）。")
        return None
    return payload


def json_or_form_editor(problem: dict, key_prefix: str, *, submit_label: str) -> None:
    """新增/编辑题目的统一入口：图形化表单 + JSON 高级模式。"""
    mode = st.radio("编辑方式", ["表单编辑（推荐）", "JSON 直接编辑"],
                    horizontal=True, key=f"{key_prefix}_mode")
    if mode.startswith("表单"):
        payload = problem_form(problem, key_prefix)
        if st.button(submit_label, type="primary", key=f"{key_prefix}_submit_form") and payload:
            _submit_problem(payload, key_prefix)
    else:
        text = st.text_area("题目配置（JSON）",
                            value=json.dumps(problem, ensure_ascii=False, indent=2),
                            height=420, key=f"{key_prefix}_json")
        if st.button(submit_label, type="primary", key=f"{key_prefix}_submit_json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                st.error(f"JSON 格式错误：{exc}")
                return
            if not isinstance(payload, dict):
                st.error("题目配置必须是一个 JSON 对象（400）。")
                return
            _submit_problem(payload, key_prefix)


def _submit_problem(payload: dict, key_prefix: str) -> None:
    """按是否已存在自动选择新增或覆盖。"""
    problem_id = str(payload.get("id") or "").strip()
    exists = any(p["id"] == problem_id for p in problem_list())
    if exists:
        result = client().update_problem(problem_id, payload)
        ok_msg = f"已覆盖保存：{problem_id}"
    else:
        result = client().create_problem(payload)
        ok_msg = f"添加成功：{problem_id}"
    if notify(result, ok_msg):
        clear_cache()


# ---------------------------------------------------------------------------
# 提交结果展示
# ---------------------------------------------------------------------------
def render_submission_detail(submission_id: str, *, show_log: bool = True) -> None:
    """渲染一条提交的详情与（可选的）测试点日志，供多个页面复用。"""
    result = client().get_submission(submission_id)
    if not result.ok:
        st.error(result.error_text())
        return
    data = result.data or {}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("提交号", f"#{data.get('submission_id')}")
    col2.metric("状态", status_text(data.get("status")))
    col3.metric("得分", f"{data.get('score') if data.get('score') is not None else '—'} / "
                        f"{data.get('counts') if data.get('counts') is not None else '—'}")
    col4.metric("峰值", f"{data.get('time') or '—'} s / {data.get('memory') or '—'} MB")

    field_row("题目", f"{data.get('problem_id')} · {problem_title(data.get('problem_id'))}")
    field_row("语言", data.get("language"))
    field_row("提交用户", data.get("user_id"))
    if data.get("compile_info"):
        st.markdown("**编译信息**")
        st.json(data["compile_info"])
    if data.get("run_info"):
        st.markdown("**运行结果**")
        st.json(data["run_info"])
    if data.get("error_info"):
        st.warning(f"错误信息：{data['error_info']}")
    if data.get("code"):
        with st.expander("查看代码"):
            st.code(data["code"], language=_pygments_language(data.get("language")))

    if show_log:
        st.markdown("**测试点明细**")
        log = client().get_log(submission_id)
        if not log.ok:
            st.info(f"无法查看测试点明细：{log.error_text()}")
        else:
            log_data = log.data or {}
            details = log_data.get("details")
            if details is None:
                st.info("该题未公开评测日志，只有本人和管理员可见；当前账号没有查看明细的权限。")
            elif not details:
                st.info("暂无测试点明细（评测可能仍在进行中）。")
            else:
                st.dataframe(
                    [{
                        "测试点": item.get("id"),
                        "结果": result_text(item.get("result")),
                        "耗时(s)": item.get("time"),
                        "内存(MB)": item.get("memory"),
                        "说明": item.get("message", ""),
                    } for item in details],
                    hide_index=True,
                )


def _pygments_language(language: str | None) -> str:
    return {"python": "python", "cpp": "cpp", "c": "c", "java": "java"}.get(language or "", "text")


def submission_table(items: list[dict]) -> None:
    """提交列表的表格展示。"""
    st.dataframe(
        [{
            "提交号": item.get("submission_id"),
            "题目": item.get("problem_id"),
            "状态": status_text(item.get("status")),
            "得分": item.get("score"),
            "总分": item.get("counts"),
        } for item in items],
        hide_index=True,
    )
