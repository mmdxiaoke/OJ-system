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

from frontend.views import ai_page, auth_page, problem_page, submission_page  # noqa: E402
from frontend.views.common import client, current_user  # noqa: E402

st.set_page_config(page_title="Python OJ", page_icon="🧪", layout="wide")

PAGES = {
    "用户中心": auth_page.render,
    "题库": problem_page.render,
    "评测中心": submission_page.render,
    "AI 智能命题": ai_page.render,
}


def main() -> None:
    st.sidebar.title("🧪 Python OJ")
    user = current_user()
    if user:
        st.sidebar.success(f"已登录：{user['username']}\n\n角色：{user['role']}")
    else:
        st.sidebar.info("未登录（部分接口会返回 401）")

    st.sidebar.caption(f"后端：{st.session_state.get('api_base', 'http://127.0.0.1:8000')}")
    choice = st.sidebar.radio("导航", list(PAGES.keys()))
    st.sidebar.divider()
    if st.sidebar.button("测试后端连通性"):
        result = client().get("/health")
        if result.ok:
            st.sidebar.success("后端在线")
        else:
            st.sidebar.error(result.error_text())
    st.sidebar.caption("程序设计训练（Python）大作业 · Step 1-6 + AI 智能命题")

    PAGES[choice]()


if __name__ == "__main__":
    main()
