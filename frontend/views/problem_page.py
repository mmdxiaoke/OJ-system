"""题目页面组：列表、详情、新增、编辑、删除、日志可见性。"""
from __future__ import annotations

import json

import streamlit as st

from frontend.views.common import client, field_row, is_admin, require_login

TEMPLATE = {
    "id": "sum_2",
    "title": "两数之和",
    "description": "输入两个整数 a, b，输出它们的和。",
    "input_description": "一行，两个整数 a 和 b，以空格分隔。",
    "output_description": "一行，输出 a+b。",
    "samples": [{"input": "1 2", "output": "3"}],
    "constraints": "|a|,|b| <= 10^9",
    "testcases": [{"input": "1 2", "output": "3"}, {"input": "-5 5", "output": "0"}],
    "hint": "有负数哦！",
    "source": "",
    "tags": ["基础题"],
    "time_limit": 1.0,
    "memory_limit": 128,
    "author": "",
    "difficulty": "入门",
}


def render() -> None:
    require_login()
    st.header("题库")
    tabs = st.tabs(["题目列表", "题目详情", "新增题目", "编辑题目", "删除题目", "日志可见性"])
    with tabs[0]:
        _list()
    with tabs[1]:
        _detail()
    with tabs[2]:
        _create()
    with tabs[3]:
        _edit()
    with tabs[4]:
        _delete()
    with tabs[5]:
        _visibility()


def _list() -> None:
    result = client().list_problems()
    if not result.ok:
        st.error(result.error_text())
        return
    problems = result.data or []
    st.caption(f"共 {len(problems)} 道题目")
    if not problems:
        st.info("题库为空，可以在「新增题目」中创建，或使用 AI 智能命题生成。")
        return
    st.dataframe(problems, hide_index=True)
    st.session_state["problem_ids"] = [p["id"] for p in problems]


def _detail() -> None:
    problem_id = st.text_input("题目 ID", key="detail_pid")
    if st.button("查看详情", key="detail_btn") and problem_id.strip():
        result = client().get_problem(problem_id.strip())
        if not result.ok:
            st.error(result.error_text())
            return
        problem = result.data or {}
        st.subheader(f"{problem.get('title', '')}（{problem.get('id')}）")
        field_row("难度", problem.get("difficulty"))
        field_row("标签", "、".join(problem.get("tags") or []))
        field_row("时间限制", f"{problem.get('time_limit')} s")
        field_row("内存限制", f"{problem.get('memory_limit')} MB")
        st.markdown("### 题目描述")
        st.write(problem.get("description", ""))
        st.markdown("### 输入格式")
        st.write(problem.get("input_description", ""))
        st.markdown("### 输出格式")
        st.write(problem.get("output_description", ""))
        st.markdown("### 样例")
        for index, sample in enumerate(problem.get("samples") or [], start=1):
            st.caption(f"样例 {index}")
            col1, col2 = st.columns(2)
            col1.code(sample.get("input", ""), language="text")
            col2.code(sample.get("output", ""), language="text")
        st.markdown("### 数据范围与提示")
        st.write(problem.get("constraints", ""))
        if problem.get("hint"):
            st.info(problem["hint"])
        with st.expander("完整配置（含测试点）"):
            st.json(problem)


def _create() -> None:
    st.caption("字段说明见 Goal.md Step 1；id 仅允许字母、数字、下划线和连字符。")
    default = st.session_state.pop("problem_editor_seed", None) or TEMPLATE
    text = st.text_area("题目配置（JSON）", value=json.dumps(default, ensure_ascii=False, indent=2), height=420)
    if st.button("提交新增", type="primary"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            st.error(f"JSON 格式错误：{exc}")
            return
        result = client().create_problem(payload)
        if result.ok:
            st.success(f"添加成功：{result.data.get('id')}")
        else:
            st.error(result.error_text())


def _edit() -> None:
    problem_id = st.text_input("要编辑的题目 ID", key="edit_pid")
    if st.button("载入当前配置", key="edit_load") and problem_id.strip():
        result = client().get_problem(problem_id.strip())
        if result.ok:
            st.session_state["edit_text"] = json.dumps(result.data, ensure_ascii=False, indent=2)
        else:
            st.error(result.error_text())
    text = st.text_area(
        "题目配置（JSON）",
        value=st.session_state.get("edit_text", json.dumps(TEMPLATE, ensure_ascii=False, indent=2)),
        height=420,
        key="edit_area",
    )
    if st.button("提交修改", type="primary"):
        if not problem_id.strip():
            st.error("请先填写题目 ID（400）。")
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            st.error(f"JSON 格式错误：{exc}")
            return
        if payload.get("id") != problem_id.strip():
            st.error("请求体中的 id 必须与路径中的题目 ID 一致（400）。")
            return
        result = client().update_problem(problem_id.strip(), payload)
        if result.ok:
            st.success(f"更新成功：{result.data.get('id')}")
        else:
            st.error(result.error_text())


def _delete() -> None:
    if not is_admin():
        st.info("删除题目仅管理员可执行（普通用户会收到 403）。")
    problem_id = st.text_input("要删除的题目 ID", key="delete_pid")
    confirm = st.checkbox("我确认删除该题目", key="delete_confirm")
    if st.button("删除", type="primary"):
        if not problem_id.strip():
            st.error("请填写题目 ID（400）。")
        elif not confirm:
            st.warning("请先勾选确认。")
        else:
            result = client().delete_problem(problem_id.strip())
            if result.ok:
                st.success(f"已删除：{result.data.get('id')}")
            else:
                st.error(result.error_text())


def _visibility() -> None:
    if not is_admin():
        st.info("日志可见性配置仅管理员可用（403）。")
    problem_id = st.text_input("题目 ID", key="vis_pid")
    public_cases = st.checkbox("允许所有登录用户查看该题评测日志详情", key="vis_flag")
    if st.button("提交配置"):
        if not problem_id.strip():
            st.error("请填写题目 ID（400）。")
            return
        result = client().set_log_visibility(problem_id.strip(), public_cases)
        if result.ok:
            st.success(f"已更新：public_cases = {result.data.get('public_cases')}")
        else:
            st.error(result.error_text())
