"""OJ 前端入口（Streamlit）。

启动方式：
    streamlit run frontend/app.py

所有数据都通过 REST API 从后端获取，前端不直接读写任何数据文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from frontend.views import (  # noqa: E402
    ai_page,
    auth_page,
    dashboard,
    problem_page,
    submission_page,
)
from frontend.views.common import clear_cache, client, current_user, role_text  # noqa: E402

st.set_page_config(page_title="Python OJ", page_icon="🧪", layout="wide")

PAGES = {
    "仪表盘": dashboard.render,
    "题库": problem_page.render,
    "评测中心": submission_page.render,
    "AI 智能命题": ai_page.render,
    "用户中心": auth_page.render,
}


def main() -> None:
    st.sidebar.title("🧪 Python OJ")
    user = current_user()

    if user:
        st.sidebar.success(f"已登录：**{user['username']}**\n\n身份：{role_text(user.get('role'))}")
        profile = client().me(user["user_id"])
        if profile.ok:
            data = profile.data or {}
            st.sidebar.caption(
                f"提交 {data.get('submit_count', 0)} 次 · 通过 {data.get('resolve_count', 0)} 题"
            )
        if st.sidebar.button("退出登录", key="sidebar_logout"):
            client().logout()
            st.session_state.user = None
            clear_cache()
            st.rerun()
    else:
        st.sidebar.info("未登录（部分接口会返回 401）")

    st.sidebar.caption(f"后端：{st.session_state.get('api_base', 'http://127.0.0.1:8000')}")
    choice = st.sidebar.radio("导航", list(PAGES.keys()))
    st.sidebar.divider()
    col1, col2 = st.sidebar.columns(2)
    if col1.button("🔄 刷新", key="sidebar_refresh", help="清空缓存并重新加载数据"):
        clear_cache()
        st.rerun()
    if col2.button("🩺 连通性", key="sidebar_ping"):
        result = client().get("/health")
        if result.ok:
            st.sidebar.success("后端在线")
        else:
            st.sidebar.error(result.error_text())
    st.sidebar.caption("程序设计训练（Python）大作业 · Step 1-6 + AI 智能命题")

    PAGES[choice]()


if __name__ == "__main__":
    main()
