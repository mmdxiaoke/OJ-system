"""评测与提交页面组：提交代码、提交记录、详情、日志、语言注册、重新评测。"""
from __future__ import annotations

import time

import streamlit as st

from frontend.views.common import client, field_row, is_admin, require_login

STATUS_EMOJI = {"pending": "⏳", "success": "✅", "error": "❌"}
RESULT_EMOJI = {"AC": "✅", "WA": "❌", "TLE": "⏰", "MLE": "💾", "RE": "💥", "CE": "🛠️", "UNK": "❓"}


def render() -> None:
    require_login()
    st.header("评测中心")
    labels = ["提交代码", "提交记录", "提交详情", "评测日志", "语言管理"]
    if is_admin():
        labels.append("重新评测")
    tabs = st.tabs(labels)
    mapping = dict(zip(labels, tabs, strict=False))
    with mapping["提交代码"]:
        _submit()
    with mapping["提交记录"]:
        _records()
    with mapping["提交详情"]:
        _detail()
    with mapping["评测日志"]:
        _log()
    with mapping["语言管理"]:
        _languages()
    if is_admin():
        with mapping["重新评测"]:
            _rejudge()


def _language_names() -> list[str]:
    result = client().list_languages()
    if result.ok:
        return (result.data or {}).get("name", []) or ["python"]
    return ["python"]


def _submit() -> None:
    languages = _language_names()
    col1, col2 = st.columns([2, 1])
    problem_id = col1.text_input("题目 ID", key="sub_pid")
    language = col2.selectbox("语言", languages, key="sub_lang")
    code = st.text_area("代码", height=320, key="sub_code",
                        placeholder="a, b = map(int, input().split())\nprint(a + b)")
    wait = st.checkbox("提交后自动轮询评测结果", value=True, key="sub_wait")
    if not st.button("提交评测", type="primary"):
        return
    if not problem_id.strip() or not code.strip():
        st.error("题目 ID 与代码不能为空（400）。")
        return
    result = client().submit(problem_id.strip(), language, code)
    if not result.ok:
        st.error(result.error_text())
        return
    submission_id = str((result.data or {}).get("submission_id"))
    st.success(f"提交成功，submission_id = {submission_id}，当前状态 pending")
    if not wait:
        return
    placeholder = st.empty()
    for _ in range(60):
        detail = client().get_submission(submission_id)
        if not detail.ok:
            placeholder.error(detail.error_text())
            return
        data = detail.data or {}
        status = data.get("status")
        placeholder.info(f"评测状态：{STATUS_EMOJI.get(status, '')} {status}")
        if status != "pending":
            placeholder.empty()
            _render_result(data)
            return
        time.sleep(0.5)
    placeholder.warning("评测仍在进行中，请稍后在「提交详情」中查看。")


def _render_result(data: dict) -> None:
    status = data.get("status")
    if status == "success":
        score = data.get("score")
        counts = data.get("counts")
        st.success(f"评测完成：得分 {score} / {counts}")
    elif status == "error":
        st.error("评测过程出现问题（status=error）")
    else:
        st.info(f"当前状态：{status}")

    compile_info = data.get("compile_info")
    run_info = data.get("run_info")
    error_info = data.get("error_info")
    if compile_info:
        st.markdown("**编译信息**")
        st.json(compile_info)
    if run_info:
        st.markdown("**运行结果**")
        st.json(run_info)
    if error_info:
        st.warning(f"错误信息：{error_info}")


def _records() -> None:
    col1, col2, col3 = st.columns(3)
    user_id = col1.text_input("user_id / 用户名（可选）", key="rec_user")
    problem_id = col2.text_input("problem_id（可选）", key="rec_pid")
    status = col3.selectbox("status（可选）", ["", "pending", "success", "error"], key="rec_status")
    col4, col5 = st.columns(2)
    page = col4.number_input("page（0 表示不传）", min_value=0, value=1, step=1)
    page_size = col5.number_input("page_size（0 表示不传）", min_value=0, value=10, step=1)

    if st.button("查询"):
        params = {
            "user_id": user_id.strip() or None,
            "problem_id": problem_id.strip() or None,
            "status": status or None,
            "page": int(page) or None,
            "page_size": int(page_size) or None,
        }
        result = client().list_submissions(**params)
        if not result.ok:
            st.error(result.error_text())
            return
        data = result.data or {}
        st.caption(f"共 {data.get('total', 0)} 条记录")
        rows = []
        for item in data.get("submissions", []):
            rows.append({
                "submission_id": item.get("submission_id"),
                "status": item.get("status"),
                "score": item.get("score"),
                "counts": item.get("counts"),
            })
        st.dataframe(rows, hide_index=True)


def _detail() -> None:
    submission_id = st.text_input("submission_id", key="det_sid")
    if st.button("查询详情") and submission_id.strip():
        result = client().get_submission(submission_id.strip())
        if not result.ok:
            st.error(result.error_text())
            return
        data = result.data or {}
        field_row("提交号", data.get("submission_id"))
        field_row("状态", data.get("status"))
        field_row("题目", data.get("problem_id"))
        field_row("语言", data.get("language"))
        field_row("用户", data.get("user_id"))
        _render_result(data)
        with st.expander("代码"):
            st.code(data.get("code", ""), language="python")


def _log() -> None:
    submission_id = st.text_input("submission_id", key="log_sid")
    if st.button("查询评测日志") and submission_id.strip():
        result = client().get_log(submission_id.strip())
        if not result.ok:
            st.error(result.error_text())
            return
        data = result.data or {}
        st.caption(f"得分 {data.get('score')} / {data.get('counts')}")
        details = data.get("details")
        if details is None:
            st.info("当前用户无权查看测试点明细（题目未公开日志）。")
            return
        if not details:
            st.info("暂无测试点明细（评测可能尚未完成）。")
            return
        rows = []
        for item in details:
            rows.append({
                "测试点": item.get("id"),
                "结果": f"{RESULT_EMOJI.get(item.get('result'), '')} {item.get('result')}",
                "耗时(s)": item.get("time"),
                "内存(MB)": item.get("memory"),
                "说明": item.get("message", ""),
            })
        st.dataframe(rows, hide_index=True)


def _languages() -> None:
    result = client().list_languages()
    if result.ok:
        st.markdown("**已注册语言**：" + "、".join((result.data or {}).get("name", [])))
    st.divider()
    st.subheader("动态注册新语言")
    st.caption("命令中可使用 {src}、{exe}、{workdir} 占位符；出于安全考虑只允许白名单编译器/解释器。")
    with st.form("lang_form"):
        name = st.text_input("语言名称", value="")
        file_ext = st.text_input("代码文件扩展名", value=".py")
        compile_cmd = st.text_input("编译命令（可选）", value="")
        run_cmd = st.text_input("运行命令", value="")
        time_limit = st.number_input("时间限制（秒）", min_value=0.1, value=1.0, step=0.5)
        memory_limit = st.number_input("内存限制（MB）", min_value=16, value=128, step=16)
        submitted = st.form_submit_button("注册")
    if submitted:
        payload = {
            "name": name.strip(),
            "file_ext": file_ext.strip(),
            "run_cmd": run_cmd.strip(),
            "time_limit": float(time_limit),
            "memory_limit": int(memory_limit),
        }
        if compile_cmd.strip():
            payload["compile_cmd"] = compile_cmd.strip()
        result = client().register_language(payload)
        if result.ok:
            st.success(f"语言已注册：{result.data.get('name')}")
        else:
            st.error(result.error_text())


def _rejudge() -> None:
    submission_id = st.text_input("submission_id", key="rej_sid")
    if st.button("重新评测"):
        if not submission_id.strip():
            st.error("请填写 submission_id（400）。")
            return
        result = client().rejudge(submission_id.strip())
        if result.ok:
            st.success(f"已重新评测，状态：{result.data.get('status')}")
        else:
            st.error(result.error_text())
