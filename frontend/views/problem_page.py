"""题目页面组：列表、详情、新增、编辑、删除、日志可见性。

交互设计：题目 ID 全部通过下拉选择，不需要用户记住或手输编号；
新增/编辑提供图形化表单（含样例与测试点逐条编辑），也保留 JSON 高级模式。
"""
from __future__ import annotations

import json

import streamlit as st

from frontend.views.common import (
    clear_cache,
    client,
    field_row,
    is_admin,
    json_or_form_editor,
    notify,
    problem_list,
    problem_selector,
    require_login,
)

TEMPLATE = {
    "id": "sum_2",
    "title": "两数之和",
    "description": "输入两个整数 a, b，输出它们的和。",
    "input_description": "一行，两个整数 a 和 b，以空格分隔。",
    "output_description": "一行，输出 a+b。",
    "samples": [{"input": "1 2", "output": "3"}],
    "constraints": "|a|,|b| <= 10^9",
    "testcases": [{"input": "1 2\n", "output": "3\n"}, {"input": "-5 5\n", "output": "0\n"}],
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
    problems = problem_list(force=True)
    col1, col2 = st.columns([5, 1])
    col1.caption(f"共 {len(problems)} 道题目；新增或编辑后列表会自动刷新。")
    if col2.button("🔄 刷新", key="problem_list_refresh"):
        clear_cache()
        st.rerun()
    if not problems:
        st.info("题库为空：可以在「新增题目」中创建，或使用「AI 智能命题」生成。")
        return
    st.dataframe(
        [{"题目 ID": p["id"], "标题": p.get("title") or "（无标题）"} for p in problems],
        hide_index=True,
    )
    st.caption("提示：下面的每个页面都可以直接用下拉框选择题目，不用手输 ID。")


def _detail() -> None:
    problem_id = problem_selector("选择要查看的题目", "detail_pick")
    if not problem_id:
        return
    result = client().get_problem(problem_id)
    if not result.ok:
        st.error(result.error_text())
        return
    problem = result.data or {}

    head, tail = st.columns([4, 1])
    head.subheader(f"{problem.get('title', '')}（{problem.get('id')}）")
    tail.download_button(
        "⬇️ 下载 JSON",
        data=json.dumps(problem, ensure_ascii=False, indent=2),
        file_name=f"{problem.get('id')}.json",
        mime="application/json",
        key="detail_download",
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("时间限制", f"{problem.get('time_limit')} s")
    col2.metric("内存限制", f"{problem.get('memory_limit')} MB")
    col3.metric("测试点", len(problem.get("testcases") or []))
    col4.metric("日志公开", "是" if problem.get("public_cases") else "否")

    field_row("难度", problem.get("difficulty"))
    field_row("标签", "、".join(problem.get("tags") or []))
    field_row("来源", problem.get("source"))
    field_row("作者", problem.get("author"))

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
    st.markdown("### 数据范围")
    st.write(problem.get("constraints", ""))
    if problem.get("hint"):
        st.info(problem["hint"])
    with st.expander("完整配置（含测试点）"):
        st.json(problem)


def _create() -> None:
    st.caption("推荐使用表单填写；标题、描述、输入格式、输出格式为必填项。"
               "若 ID 已存在，会自动切换为覆盖保存。")
    if st.button("插入示例模板", key="create_template"):
        st.session_state["create_seed"] = TEMPLATE
        st.rerun()
    seed = st.session_state.get("create_seed") or TEMPLATE
    json_or_form_editor(seed, "create", submit_label="提交新增")


def _edit() -> None:
    problem_id = problem_selector("选择要编辑的题目", "edit_pick")
    if not problem_id:
        return
    result = client().get_problem(problem_id)
    if not result.ok:
        st.error(result.error_text())
        return
    st.caption(f"正在编辑 {problem_id}；表单已自动载入当前配置，保存后会覆盖原题目。")
    json_or_form_editor(result.data or {}, f"edit_{problem_id}", submit_label="提交修改")


def _delete() -> None:
    if not is_admin():
        st.info("删除题目仅管理员可执行，普通用户提交会收到 403。")
    problem_id = problem_selector("选择要删除的题目", "delete_pick")
    if not problem_id:
        return
    st.warning(f"即将删除题目 {problem_id}，该操作不可撤销。")
    confirm = st.checkbox("我确认删除该题目", key="delete_confirm")
    if st.button("删除题目", type="primary", key="delete_btn"):
        if not confirm:
            st.warning("请先勾选确认。")
            return
        result = client().delete_problem(problem_id)
        if notify(result, f"已删除：{problem_id}"):
            # 清缓存即可：下一轮 problem_selector 会在创建控件前丢弃失效的选中值
            clear_cache()


def _visibility() -> None:
    if not is_admin():
        st.info("日志可见性配置仅管理员可用，普通用户提交会收到 403。")
    problem_id = problem_selector("选择题目", "vis_pick")
    if not problem_id:
        return
    detail = client().get_problem(problem_id)
    current = bool((detail.data or {}).get("public_cases")) if detail.ok else False
    st.caption(f"当前设置：public_cases = {current}")
    public_cases = st.toggle(
        "允许所有登录用户查看该题评测日志的测试点明细",
        value=current, key=f"vis_toggle_{problem_id}",
    )
    if st.button("保存可见性设置", type="primary", key="vis_save"):
        result = client().set_log_visibility(problem_id, bool(public_cases))
        if notify(result, "可见性已更新"):
            clear_cache()
