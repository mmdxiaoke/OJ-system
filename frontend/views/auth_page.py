"""用户页面组：注册、登录、退出、个人信息、用户管理。"""
from __future__ import annotations

import streamlit as st

from frontend.views.common import (
    client,
    current_user,
    field_row,
    is_admin,
    notify,
    rebuild_client,
    require_admin,
    show_data,
)

ROLES = ["user", "admin", "banned"]


def render() -> None:
    st.header("用户中心")
    user = current_user()
    tabs = ["登录 / 注册", "我的信息"]
    if is_admin():
        tabs.append("用户管理")
    tabs.append("系统设置")
    tab_objects = st.tabs(tabs)
    mapping = dict(zip(tabs, tab_objects, strict=False))

    with mapping["登录 / 注册"]:
        _login_register(user)
    with mapping["我的信息"]:
        _profile(user)
    if is_admin():
        with mapping["用户管理"]:
            _admin_panel()
    with mapping["系统设置"]:
        _settings()


def _login_register(user: dict | None) -> None:
    if user:
        st.info(f"当前已登录：**{user['username']}**（角色：{user['role']}）")
        if st.button("退出登录", type="primary"):
            result = client().logout()
            st.session_state.user = None
            notify(result, "已退出登录")
            st.rerun()
        return

    left, right = st.columns(2)
    with left:
        st.subheader("登录")
        with st.form("login_form"):
            username = st.text_input("用户名", key="login_username")
            password = st.text_input("密码", type="password", key="login_password")
            submitted = st.form_submit_button("登录", type="primary", key="login_submit")
        if submitted:
            if not username or not password:
                st.error("用户名和密码不能为空（400）。")
            else:
                result = client().login(username, password)
                if result.ok:
                    st.session_state.user = result.data
                    st.success("登录成功")
                    st.rerun()
                else:
                    # 401 用户名或密码错误 / 403 用户被禁用
                    st.error(result.error_text())

    with right:
        st.subheader("注册")
        with st.form("register_form"):
            new_name = st.text_input("用户名（3-40 字符）", key="reg_username")
            new_pwd = st.text_input("密码（至少 6 位）", type="password", key="reg_password")
            new_pwd2 = st.text_input("确认密码", type="password", key="reg_password2")
            submitted = st.form_submit_button("注册", key="register_submit")
        if submitted:
            if len(new_name.strip()) < 3 or len(new_name.strip()) > 40:
                st.error("用户名长度需在 3-40 字符之间（400）。")
            elif len(new_pwd) < 6:
                st.error("密码至少 6 位（400）。")
            elif new_pwd != new_pwd2:
                st.error("两次输入的密码不一致。")
            else:
                result = client().register(new_name.strip(), new_pwd)
                if result.ok:
                    st.success(f"注册成功，user_id = {result.data.get('user_id')}，请登录。")
                else:
                    st.error(result.error_text())


def _profile(user: dict | None) -> None:
    if not user:
        st.warning("请先登录。")
        return
    target_id = st.text_input("查询用户 ID（默认查询自己）", value=str(user["user_id"]), key="profile_uid")
    if st.button("查询", key="profile_query"):
        result = client().me(target_id.strip())
        if show_data(result):
            data = result.data or {}
            col1, col2 = st.columns(2)
            with col1:
                field_row("用户 ID", data.get("user_id"))
                field_row("用户名", data.get("username"))
                field_row("角色", data.get("role"))
            with col2:
                field_row("注册时间", data.get("join_time"))
                field_row("提交数", data.get("submit_count"))
                field_row("通过题目数", data.get("resolve_count"))


def _admin_panel() -> None:
    require_admin()
    st.subheader("用户列表")
    col1, col2 = st.columns(2)
    page = col1.number_input("页码", min_value=1, value=1, step=1)
    page_size = col2.number_input("每页数量", min_value=1, value=10, step=1)
    result = client().list_users(page=int(page), page_size=int(page_size))
    if not result.ok:
        st.error(result.error_text())
        return
    data = result.data or {}
    st.caption(f"共 {data.get('total', 0)} 位用户")
    st.dataframe(data.get("users", []), hide_index=True)

    st.divider()
    st.subheader("变更用户权限")
    with st.form("role_form"):
        target = st.text_input("用户 ID")
        role = st.selectbox("新角色", ROLES)
        submitted = st.form_submit_button("提交变更")
    if submitted:
        if not target.strip():
            st.error("用户 ID 不能为空（400）。")
        else:
            notify(client().set_role(target.strip(), role), "权限已更新")

    st.divider()
    st.subheader("创建管理员账户")
    with st.form("admin_form"):
        name = st.text_input("用户名")
        pwd = st.text_input("密码", type="password")
        submitted = st.form_submit_button("创建")
    if submitted:
        if len(name.strip()) < 3 or len(pwd) < 6:
            st.error("用户名至少 3 字符、密码至少 6 位（400）。")
        else:
            result = client().create_admin(name.strip(), pwd)
            if result.ok:
                st.success(f"管理员已创建：{result.data.get('username')}")
            else:
                st.error(result.error_text())


def _settings() -> None:
    st.subheader("后端连接")
    base = st.text_input("后端地址", value=st.session_state.get("api_base", "http://127.0.0.1:8000"))
    if st.button("应用并重连"):
        st.session_state.api_base = base.strip()
        rebuild_client(base.strip())
        st.success("已重新连接后端，请重新登录。")
        st.rerun()

    st.divider()
    st.caption("提示：会话保存在后端，Cookie 由 requests.Session 自动携带；"
               "所有权限判断均以后端返回的状态码为准。")
