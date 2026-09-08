"""用户页面组：注册、登录、退出、个人信息、用户管理。"""
from __future__ import annotations

import streamlit as st

from frontend.views.common import (
    clear_cache,
    client,
    current_user,
    is_admin,
    notify,
    rebuild_client,
    require_admin,
    role_text,
    show_data,
    submission_table,
)

ROLES = ["user", "admin", "banned"]
ROLE_FORMAT = {"user": "普通用户 user", "admin": "管理员 admin", "banned": "禁用 banned"}


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
        st.info(f"当前已登录：**{user['username']}**（{role_text(user.get('role'))}）")
        col1, col2 = st.columns([1, 4])
        if col1.button("退出登录", type="primary", key="logout_btn"):
            result = client().logout()
            st.session_state.user = None
            clear_cache()
            notify(result, "已退出登录")
            st.rerun()
        col2.caption("退出后需要重新登录才能提交代码、查看评测结果。")
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
                    clear_cache()
                    st.success(f"登录成功，欢迎 {result.data.get('username')}")
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
                    # 注册成功后把用户名填进登录框，省去再输一次
                    st.session_state["login_username"] = new_name.strip()
                    st.success(f"注册成功，user_id = {result.data.get('user_id')}；用户名已填入左侧登录框，输入密码即可登录。")
                else:
                    st.error(result.error_text())


def _profile(user: dict | None) -> None:
    if not user:
        st.warning("请先登录。")
        return

    st.caption("默认展示你自己的信息；管理员可以填写其他用户 ID 查看。")
    col1, col2 = st.columns([3, 1])
    target_id = col1.text_input("用户 ID", value=str(user["user_id"]), key="profile_uid")
    col2.write("")
    col2.write("")
    reload_clicked = col2.button("🔄 刷新", key="profile_reload")
    if reload_clicked:
        clear_cache()

    result = client().me(target_id.strip())
    if not show_data(result):
        return
    data = result.data or {}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("用户 ID", data.get("user_id"))
    col2.metric("用户名", data.get("username"))
    col3.metric("角色", role_text(data.get("role")))
    col4.metric("注册时间", data.get("join_time"))
    col1, col2 = st.columns(2)
    col1.metric("提交数（按提交算）", data.get("submit_count"))
    col2.metric("通过题目数（按题目算）", data.get("resolve_count"))

    if str(target_id.strip()) == str(user["user_id"]):
        st.divider()
        st.subheader("我的最近提交")
        recent = client().list_submissions(user_id=user["user_id"], page=1, page_size=5)
        items = (recent.data or {}).get("submissions", []) if recent.ok else []
        if items:
            submission_table(items)
            st.caption("到「评测中心 → 提交详情」可以从下拉列表中直接选择这些提交查看测试点明细。")
        else:
            st.info("还没有提交记录。")


def _admin_panel() -> None:
    require_admin()
    st.subheader("用户列表")
    col1, col2 = st.columns(2)
    page = col1.number_input("页码", min_value=1, value=1, step=1, key="users_page")
    page_size = col2.number_input("每页数量", min_value=1, value=20, step=5, key="users_page_size")
    result = client().list_users(page=int(page), page_size=int(page_size))
    if not result.ok:
        st.error(result.error_text())
        return
    data = result.data or {}
    users = data.get("users", [])
    st.caption(f"共 {data.get('total', 0)} 位用户")
    st.dataframe(
        [{
            "用户 ID": u.get("user_id"),
            "用户名": u.get("username"),
            "角色": role_text(u.get("role")),
            "注册时间": u.get("join_time"),
            "提交数": u.get("submit_count"),
            "通过数": u.get("resolve_count"),
        } for u in users],
        hide_index=True,
    )

    st.divider()
    st.subheader("变更用户权限")
    if not users:
        st.info("当前页没有用户，先调整页码。")
    else:
        options = [str(u["user_id"]) for u in users]
        labels = {str(u["user_id"]): f"{u['user_id']} · {u['username']}（{role_text(u.get('role'))}）"
                  for u in users}
        with st.form("role_form"):
            target = st.selectbox("选择用户", options, key="role_target",
                                  format_func=lambda v: labels.get(v, v))
            role = st.selectbox("新角色", ROLES, key="role_value",
                                format_func=lambda v: ROLE_FORMAT.get(v, v))
            submitted = st.form_submit_button("提交变更", type="primary", key="role_submit")
        if submitted:
            res = client().set_role(target, role)
            if notify(res, f"已将 {labels.get(target, target)} 的角色改为 {ROLE_FORMAT.get(role, role)}"):
                clear_cache()
                if target == str(current_user().get("user_id")) and role != "admin":
                    st.warning("你刚刚修改了自己的权限，重新登录后生效。")

    st.divider()
    st.subheader("创建管理员账户")
    with st.form("admin_form"):
        name = st.text_input("用户名", key="new_admin_name")
        pwd = st.text_input("密码", type="password", key="new_admin_pwd")
        submitted = st.form_submit_button("创建", key="admin_submit")
    if submitted:
        if len(name.strip()) < 3 or len(pwd) < 6:
            st.error("用户名至少 3 字符、密码至少 6 位（400）。")
        else:
            result = client().create_admin(name.strip(), pwd)
            if result.ok:
                st.success(f"管理员已创建：{result.data.get('username')}")
                clear_cache()
            else:
                st.error(result.error_text())


def _settings() -> None:
    st.subheader("后端连接")
    base = st.text_input("后端地址", value=st.session_state.get("api_base", "http://127.0.0.1:8000"),
                         key="api_base_input")
    col1, col2 = st.columns([1, 3])
    if col1.button("应用并重连", key="apply_base"):
        st.session_state.api_base = base.strip()
        rebuild_client(base.strip())
        st.success("已重新连接后端，请重新登录。")
        st.rerun()
    if col2.button("测试连接", key="test_base"):
        result = client().get("/health")
        if result.ok:
            st.success(f"后端在线：{(result.data or {}).get('data_dir', '')}")
        else:
            st.error(result.error_text())

    st.divider()
    st.caption("提示：会话保存在后端，Cookie 由 requests.Session 自动携带；"
               "所有权限判断均以后端返回的状态码为准，前端隐藏按钮不作为权限依据。")
    st.caption("账号被设为 banned 后，登录会返回 403，已登录的会话访问任意接口也会返回 403。")
