"""评测与提交页面组：提交代码、提交记录、详情、日志、语言管理、重新评测。

交互设计：
* 题目、语言、提交记录全部用下拉选择，不需要手输编号；
* 提交后自动轮询并展示进度条与最终结果；
* 提交记录页可以直接展开某一条的详情与测试点明细。
"""
from __future__ import annotations

import time

import streamlit as st

from frontend.views.common import (
    CODE_TEMPLATES,
    clear_cache,
    client,
    is_admin,
    pager,
    problem_selector,
    render_submission_detail,
    require_login,
    status_text,
    submission_selector,
    submission_table,
)

LANGUAGE_PRESETS = {
    "python": {"name": "python", "file_ext": ".py", "run_cmd": "python3 {src}"},
    "cpp": {"name": "cpp", "file_ext": ".cpp", "compile_cmd": "g++ {src} -O2 -std=c++14 -o {exe}",
            "run_cmd": "{exe}"},
    "c": {"name": "c", "file_ext": ".c", "compile_cmd": "gcc {src} -O2 -std=c11 -o {exe}",
          "run_cmd": "{exe}"},
    "java": {"name": "java", "file_ext": ".java", "compile_cmd": "javac {src}", "run_cmd": "java Main"},
}


def render() -> None:
    require_login()
    st.header("评测中心")
    labels = ["提交代码", "提交记录", "提交详情", "语言管理"]
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
    problem_id = problem_selector("选择题目", "submit_pick", allow_empty=True, empty_label="（请选择题目）")
    # 默认选中 python（最常用），没有 python 时退回第一个语言
    default_index = languages.index("python") if "python" in languages else 0
    language = st.selectbox("语言", languages, index=default_index, key="sub_lang")

    col1, col2 = st.columns([1, 4])
    if col1.button("插入代码模板", key="insert_template"):
        st.session_state["sub_code"] = CODE_TEMPLATES.get(language, CODE_TEMPLATES["python"])
        st.rerun()
    col2.caption("模板会插入到下面的代码框；也可以直接粘贴自己的代码。")

    code = st.text_area("代码", height=320, key="sub_code",
                        placeholder="a, b = map(int, input().split())\nprint(a + b)")
    wait = st.checkbox("提交后自动轮询评测结果", value=True, key="sub_wait")

    if not st.button("提交评测", type="primary", key="submit_btn"):
        return
    if not problem_id:
        st.error("请先选择题目。")
        return
    if not code.strip():
        st.error("代码不能为空（400）。")
        return

    result = client().submit(problem_id, language, code)
    if not result.ok:
        st.error(result.error_text())
        return
    submission_id = str((result.data or {}).get("submission_id"))
    st.success(f"提交成功，submission_id = {submission_id}，当前状态 pending")
    clear_cache()

    if not wait:
        st.info("可以到「提交详情」页面从下拉列表中选择这条提交查看结果。")
        return

    progress = st.progress(0.0, text="正在评测…")
    placeholder = st.empty()
    for step in range(60):
        detail = client().get_submission(submission_id)
        if not detail.ok:
            progress.empty()
            placeholder.error(detail.error_text())
            return
        data = detail.data or {}
        status = data.get("status")
        progress.progress(min(0.95, (step + 1) / 60), text=f"评测状态：{status_text(status)}")
        if status != "pending":
            progress.empty()
            placeholder.empty()
            render_submission_detail(submission_id)
            return
        time.sleep(0.5)
    progress.empty()
    placeholder.warning("评测仍在进行中，请稍后在「提交详情」中查看。")


def _records() -> None:
    user = require_login()
    st.caption("不填 user_id 时：管理员可查看该题所有同学的记录，普通用户只能看到自己的。")
    with st.expander("筛选条件", expanded=True):
        col1, col2, col3 = st.columns(3)
        mine = col1.checkbox("只看我自己", value=True, key="rec_mine")
        problem_id = problem_selector("题目（可选）", "rec_pick", allow_empty=True,
                                      empty_label="（全部题目）", show_refresh=False)
        status = col2.selectbox("状态（可选）", ["", "pending", "success", "error"], key="rec_status")
        page_size = col3.number_input("每页数量", min_value=1, max_value=50, value=10, key="rec_page_size")

    page = int(st.session_state.get("rec_page", 1))
    params = {
        "problem_id": problem_id,
        "status": status or None,
        "page": page,
        "page_size": int(page_size),
    }
    if mine:
        params["user_id"] = user["user_id"]
    elif not problem_id:
        st.info("未勾选「只看我自己」时，需要至少选择一个题目才能查询。")
        return

    result = client().list_submissions(**params)
    if not result.ok:
        st.error(result.error_text())
        return
    data = result.data or {}
    total = data.get("total", 0)
    items = data.get("submissions", [])

    page = pager(total, page, int(page_size), "rec")
    st.session_state["rec_page"] = page
    if not items:
        st.info("没有符合条件的提交记录。")
        return
    submission_table(items)

    ids = [str(item["submission_id"]) for item in items]
    col1, col2 = st.columns([4, 1])
    chosen = col1.selectbox("选择一条记录查看详情", ids, key="rec_detail_pick",
                            format_func=lambda v: next(
                                (f"#{i['submission_id']} · {i.get('problem_id')} · {status_text(i.get('status'))}"
                                 for i in items if str(i["submission_id"]) == v), v))
    if col2.button("查看详情", key="rec_detail_btn"):
        st.session_state["record_detail_id"] = chosen
    detail_id = st.session_state.get("record_detail_id")
    if detail_id:
        st.divider()
        st.subheader(f"提交 #{detail_id} 的详情")
        render_submission_detail(str(detail_id))


def _detail() -> None:
    st.caption("直接从你最近的提交中选择即可，也可以手动输入提交号。")
    submission_id = submission_selector("选择提交记录", "detail_sid")
    if not submission_id:
        return
    if st.session_state.get("_detail_poll_id") != submission_id:
        st.session_state["_detail_poll_id"] = submission_id
        st.session_state["_detail_poll"] = 0

    col1, col2 = st.columns([1, 5])
    if col1.button("🔄 刷新", key="detail_reload"):
        clear_cache()
        st.rerun()
    auto = col2.checkbox("评测中时自动刷新（每 1 秒，最多 120 次）", value=True, key="detail_auto")
    if auto:
        result = client().get_submission(submission_id)
        status = (result.data or {}).get("status") if result.ok else None
        if status == "pending":
            polls = int(st.session_state.get("_detail_poll", 0)) + 1
            st.session_state["_detail_poll"] = polls
            if polls <= 120:
                time.sleep(1.0)
                st.rerun()
            else:
                st.info("自动刷新已达上限，可点击「刷新」按钮继续查看。")
        else:
            st.session_state["_detail_poll"] = 0
    st.divider()
    render_submission_detail(submission_id)


def _languages() -> None:
    result = client().list_languages()
    if result.ok:
        names = (result.data or {}).get("name", [])
        st.markdown("**已注册语言**：" + "、".join(names))
    st.caption("命令中可使用 {src}、{exe}、{workdir} 占位符；"
               "出于安全考虑只允许白名单编译器/解释器，且命令不经过 shell 执行。")
    st.divider()
    st.subheader("动态注册新语言")
    preset_name = st.selectbox("快速填充常用语言", ["（自定义）", *LANGUAGE_PRESETS.keys()],
                               key="lang_preset")
    preset = LANGUAGE_PRESETS.get(preset_name, {})
    with st.form("lang_form"):
        name = st.text_input("语言名称", value=preset.get("name", ""))
        file_ext = st.text_input("代码文件扩展名", value=preset.get("file_ext", ".py"))
        compile_cmd = st.text_input("编译命令（解释型语言留空）", value=preset.get("compile_cmd", ""))
        run_cmd = st.text_input("运行命令", value=preset.get("run_cmd", "python3 {src}"))
        col1, col2 = st.columns(2)
        time_limit = col1.number_input("时间限制（秒）", min_value=0.1, max_value=60.0,
                                       value=1.0, step=0.5)
        memory_limit = col2.number_input("内存限制（MB）", min_value=16, max_value=4096,
                                         value=128, step=16)
        submitted = st.form_submit_button("注册语言", type="primary")
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
        res = client().register_language(payload)
        if res.ok:
            st.success(f"语言已注册：{res.data.get('name')}")
            clear_cache()
        else:
            st.error(res.error_text())


def _rejudge() -> None:
    st.caption("重新评测会覆盖原提交的结果，仅管理员可执行。")
    submission_id = submission_selector("选择要重新评测的提交", "rejudge_sid", limit=50)
    if not submission_id:
        return
    if st.button("重新评测", type="primary"):
        result = client().rejudge(submission_id)
        if result.ok:
            st.success(f"已重新评测，当前状态：{status_text(result.data.get('status'))}")
            clear_cache()
        else:
            st.error(result.error_text())
    with st.expander("管理员：按提交号重新评测任意提交"):
        manual = st.text_input("submission_id", key="rejudge_manual")
        if st.button("重新评测该提交", key="rejudge_manual_btn") and manual.strip():
            result = client().rejudge(manual.strip())
            if result.ok:
                st.success(f"已重新评测 #{manual.strip()}")
                clear_cache()
            else:
                st.error(result.error_text())
