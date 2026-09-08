"""仪表盘：登录后的总览页，减少在页面之间来回找信息。"""
from __future__ import annotations

import streamlit as st

from frontend.views.common import (
    client,
    current_user,
    is_admin,
    problem_list,
    role_text,
    submission_table,
)


def render() -> None:
    user = current_user()
    if not user:
        _welcome_guest()
        return

    st.header(f"你好，{user['username']} 👋")
    st.caption(f"当前身份：{role_text(user.get('role'))}")

    problems = problem_list(force=True)
    me = client().me(user["user_id"])
    profile = me.data if me.ok else {}

    recent = client().list_submissions(user_id=user["user_id"], page=1, page_size=5)
    recent_items = (recent.data or {}).get("submissions", []) if recent.ok else []
    total_submissions = (recent.data or {}).get("total", 0) if recent.ok else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("题库题目", len(problems))
    col2.metric("我的提交", total_submissions)
    col3.metric("通过题目", profile.get("resolve_count", 0))
    col4.metric("注册时间", profile.get("join_time", "—"))

    if is_admin():
        users = client().list_users(page=1, page_size=1)
        audits = client().access_logs(page=1, page_size=5)
        col1, col2 = st.columns(2)
        col1.metric("系统用户数", (users.data or {}).get("total", 0) if users.ok else "—")
        col2.metric("最近日志访问", len(audits.data or []) if audits.ok else "—")

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.subheader("我的最近提交")
        if recent_items:
            submission_table(recent_items)
            st.caption("提示：到「评测中心 → 提交详情」可以从下拉列表里直接选择这些提交查看明细。")
        else:
            st.info("还没有提交记录，去「评测中心 → 提交代码」试试吧。")

    with right:
        st.subheader("快捷操作")
        st.markdown(
            "- **提交代码**：评测中心 → 提交代码（题目和语言都可以下拉选择）\n"
            "- **查看结果**：评测中心 → 提交详情（自动列出你最近的提交）\n"
            "- **看测试点**：提交详情页会一并展示测试点明细\n"
            "- **出题**：题库 → 新增题目（表单填写），或 AI 智能命题一键生成\n"
            "- **改密码以外的账号信息**：用户中心"
        )
        if not problems:
            st.warning("题库还是空的，可以先在「题库 → 新增题目」里用表单创建一道题。")

    st.divider()
    st.subheader("题库速览")
    if problems:
        st.dataframe(
            [{"题目 ID": p["id"], "标题": p.get("title") or "（无标题）"} for p in problems[:10]],
            hide_index=True,
        )
        if len(problems) > 10:
            st.caption(f"仅显示前 10 道，共 {len(problems)} 道。")
    else:
        st.info("题库为空。")


def _welcome_guest() -> None:
    st.header("欢迎使用 Python OJ 🧪")
    st.markdown(
        "这是一个小型 Online Judge 系统，支持 **题目管理 / 多语言评测 / 评测日志 / 用户权限**，"
        "并提供 **AI 智能命题** 功能。\n\n"
        "开始使用前请先到左侧「用户中心」注册或登录：\n\n"
        "1. 注册一个账号（用户名 3-40 字符，密码至少 6 位）；\n"
        "2. 登录后在「题库」里选择或创建题目；\n"
        "3. 到「评测中心 → 提交代码」提交解答，提交后会自动轮询评测结果；\n"
        "4. 想看每个测试点的情况，到「提交详情」查看明细。"
    )
    result = client().get("/health")
    if result.ok:
        st.success("后端连接正常。")
    else:
        st.error(f"后端连接失败：{result.error_text()}\n\n请确认后端已启动（`python run.py backend`）。")
