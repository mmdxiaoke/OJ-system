"""页面公共工具：会话状态、统一提示。"""
from __future__ import annotations

import streamlit as st

from frontend.api_client import ApiResult, OJClient

DEFAULT_BASE = "http://127.0.0.1:8000"


def client() -> OJClient:
    if "client" not in st.session_state:
        st.session_state.client = OJClient(st.session_state.get("api_base", DEFAULT_BASE))
    return st.session_state.client


def rebuild_client(base_url: str) -> None:
    st.session_state.client = OJClient(base_url)
    st.session_state.user = None


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
