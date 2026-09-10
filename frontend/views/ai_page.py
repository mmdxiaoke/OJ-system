"""AI 智能命题页面（Advance R1~R4）。

交互设计：模型配置提供「填充示例」按钮而不是写死默认值（提供商、模型、密钥始终由用户决定）；
任务列表用下拉选择 + 展开详情，进度以进度条与阶段列表实时展示。
"""
from __future__ import annotations

import streamlit as st

from frontend.views.common import clear_cache, client, field_row, require_login

STATUS_TEXT = {
    "pending": "等待执行",
    "running": "执行中",
    "success": "已完成",
    "failed": "失败",
    "cancelled": "已中断",
}
STAGE_ORDER = ["analyze", "statement", "solution", "generator", "verify", "finalize"]

# 仅作为「填充示例」，不代表默认配置；实际请求完全使用用户填写的值
EXAMPLE_CONFIG = {
    "provider_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "input_price": 1.0,
    "output_price": 2.0,
    "price_unit": 1000000,
}


def render() -> None:
    require_login()
    st.header("AI 智能命题")
    tabs = st.tabs(["模型配置", "开始命题", "任务列表"])
    with tabs[0]:
        _model_config()
    with tabs[1]:
        _compose()
    with tabs[2]:
        _task_list()


def _model_config() -> None:
    st.caption("提供商 URL、模型名称与密钥都可以自由配置，保存后会实际用于后续请求；"
               "密钥不会在任何查询接口中返回明文。")
    current = client().get_model_config()
    if current.ok:
        data = current.data or {}
        col1, col2, col3 = st.columns(3)
        col1.metric("提供商 URL", data.get("provider_url") or "未配置")
        col2.metric("模型", data.get("model") or "未配置")
        col3.metric("密钥", "已配置" if data.get("api_key_configured") else "未配置")
        st.caption(
            f"计价：输入 {data.get('input_price')} / 输出 {data.get('output_price')} "
            f"（每 {data.get('price_unit')} tokens）"
        )

    if st.button("填充示例配置（可自由修改）", key="fill_example"):
        st.session_state["cfg_url"] = EXAMPLE_CONFIG["provider_url"]
        st.session_state["cfg_model"] = EXAMPLE_CONFIG["model"]
        st.session_state["cfg_in"] = EXAMPLE_CONFIG["input_price"]
        st.session_state["cfg_out"] = EXAMPLE_CONFIG["output_price"]
        st.session_state["cfg_unit"] = EXAMPLE_CONFIG["price_unit"]
        st.rerun()

    with st.form("model_config_form"):
        provider_url = st.text_input(
            "提供商 URL", key="cfg_url",
            placeholder="OpenAI 兼容接口，例如 https://your-provider.example/v1",
            help="填写到 /v1 即可，系统会自动补上 /chat/completions",
        )
        model = st.text_input("模型名称", key="cfg_model", placeholder="例如 your-model-name")
        api_key = st.text_input("模型密钥", type="password", value="", key="cfg_key",
                                help="留空表示沿用已保存的密钥")
        col1, col2, col3 = st.columns(3)
        input_price = col1.number_input("输入单价", min_value=0.0, value=1.0, step=0.1,
                                        format="%.4f", key="cfg_in")
        output_price = col2.number_input("输出单价", min_value=0.0, value=2.0, step=0.1,
                                         format="%.4f", key="cfg_out")
        price_unit = col3.number_input("计价单位（tokens）", min_value=1, value=1000000,
                                       step=1000, key="cfg_unit")
        submitted = st.form_submit_button("保存配置", type="primary", key="save_config")
    if submitted:
        payload = {
            "provider_url": provider_url.strip(),
            "model": model.strip(),
            "input_price": float(input_price),
            "output_price": float(output_price),
            "price_unit": int(price_unit),
        }
        if api_key.strip():
            payload["api_key"] = api_key.strip()
        result = client().set_model_config(payload)
        if result.ok:
            st.success("模型配置已保存")
            st.json(result.data)
        else:
            st.error(result.error_text())


def _compose() -> None:
    st.caption("输入必须覆盖的知识点与难度要求，系统会完成题面设计、标程编写、数据生成与校验，"
               "并把每个测试点真正跑一遍验证。")
    with st.form("ai_task_form"):
        requirement = st.text_area(
            "命题需求", height=140, key="ai_requirement",
            placeholder="为一节讲「单调栈」的课程设计一道题，要求考察下一个更大元素的求解，"
                        "并能让 O(n^2) 的暴力解超时。",
        )
        col1, col2 = st.columns(2)
        difficulty = col1.selectbox("期望难度", ["", "入门", "普及-", "普及/提高-", "提高+"],
                                    key="ai_difficulty")
        case_count = col2.number_input("测试点数量", min_value=3, max_value=30, value=12,
                                       key="ai_case_count",
                                       help="建议 8-15 个，至少 3 个小数据用于交叉验证")
        knowledge = st.text_input("必须覆盖的知识点（用逗号分隔）", value="", key="ai_knowledge")
        problem_id = st.text_input("参考/改编的已有题目 ID（可选）", value="", key="ai_problem_id",
                                   help="留空表示从零出题；填写后会读取该题配置作为改编基础")
        mode = st.radio("执行方式", ["实时观察进度（SSE）", "后台执行（稍后查询）"],
                        horizontal=True, key="ai_mode")
        submitted = st.form_submit_button("开始命题", type="primary", key="start_task")

    if not submitted:
        return
    if not requirement.strip():
        st.error("命题需求不能为空（400）。")
        return
    payload = {
        "requirement": requirement.strip(),
        "difficulty": difficulty or None,
        "knowledge_points": [k.strip() for k in knowledge.split(",") if k.strip()],
        "case_count": int(case_count),
    }
    if problem_id.strip():
        payload["problem_id"] = problem_id.strip()

    result = client().create_ai_task(payload)
    if not result.ok:
        st.error(result.error_text())
        return
    task_id = (result.data or {}).get("task_id")
    st.success(f"任务已创建：{task_id}")
    st.session_state["ai_task_id"] = task_id

    if mode.startswith("后台"):
        st.info("任务在后台执行，可在「任务列表」中查看进度、Token 用量并中断任务。")
        return
    _watch(task_id)


def _watch(task_id: str) -> None:
    """通过 SSE 实时展示进度、增量输出与 Token 用量。"""
    progress_box = st.empty()
    bar = st.progress(0.0, text="正在连接模型服务…")
    stage_box = st.container()
    usage_box = st.empty()
    seen: list[str] = []
    value = 0.05

    for event, data in client().ai_events(task_id):
        if event == "snapshot":
            status = data.get("status")
            bar.progress(value, text=f"任务状态：{STATUS_TEXT.get(status, status)}")
        elif event == "progress":
            message = data.get("message", "")
            stage = data.get("stage", "")
            index = STAGE_ORDER.index(stage) + 1 if stage in STAGE_ORDER else 1
            value = max(value, min(0.95, index / len(STAGE_ORDER)))
            bar.progress(value, text=message or "处理中…")
            if not seen or seen[-1] != message:
                seen.append(message)
                with stage_box:
                    st.write(f"· {message}")
        elif event == "delta":
            bar.progress(value, text="模型正在生成内容…")
        elif event == "usage":
            usage_box.caption(
                f"已累计 Token：输入 {data.get('input_tokens', 0)} / 输出 {data.get('output_tokens', 0)}"
            )
        elif event == "status":
            status = data.get("status")
            bar.progress(1.0, text=f"任务状态：{STATUS_TEXT.get(status, status)}")
            progress_box.success(f"任务状态：{STATUS_TEXT.get(status, status)}")
            if data.get("usage"):
                usage_box.json(data["usage"])
            if data.get("error"):
                st.error(data["error"])
            break
        elif event == "error":
            bar.empty()
            st.error(data.get("message", "进度连接中断"))
            break
        elif event == "heartbeat":
            continue
    _show_result(task_id)


def _show_result(task_id: str) -> None:
    result = client().get_ai_task(task_id)
    if not result.ok:
        st.error(result.error_text())
        return
    task = result.data or {}
    st.subheader("任务结果")
    field_row("状态", STATUS_TEXT.get(task.get("status"), task.get("status")))
    field_row("进度", task.get("progress"))
    usage = task.get("usage") or {}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("输入 Token", usage.get("input_tokens", 0))
    col2.metric("输出 Token", usage.get("output_tokens", 0))
    col3.metric("总 Token", usage.get("total_tokens", 0))
    col4.metric("费用", f"{usage.get('cost', 0)} {usage.get('currency', 'USD')}")
    if usage.get("estimated"):
        st.caption("注意：模型接口未返回完整 usage，Token 数量为估算值。")
    st.caption(
        f"计价依据：输入 {usage.get('input_price', 0)} / 输出 {usage.get('output_price', 0)} "
        f"每 {usage.get('price_unit', 1000000)} tokens；"
        "费用 = 输入 Token/单位×单价 + 输出 Token/单位×单价。"
    )

    payload = task.get("result")
    if not payload:
        return
    problem = payload.get("problem") or {}
    st.markdown("#### 生成的题目配置")
    st.json(problem)
    verification = payload.get("verification") or {}
    st.markdown("#### 测试数据校验")
    st.json(verification)
    with st.expander("参考程序 / 暴力程序 / 数据生成脚本"):
        st.code(payload.get("reference_code", ""), language="python")
        st.code(payload.get("brute_code", ""), language="python")
        st.code(payload.get("generator_code", ""), language="python")

    st.markdown("#### 导入题库")
    mode = st.radio("导入方式", ["create", "update"], horizontal=True, key=f"apply_mode_{task_id}",
                    help="create 用于新题目，update 用于覆盖已有题目")
    col1, col2 = st.columns([1, 4])
    if col1.button("导入到题库", type="primary", key=f"apply_{task_id}"):
        apply_result = client().apply_ai_task(task_id, mode)
        if apply_result.ok:
            st.success(f"已导入题目：{apply_result.data.get('id')}，可在「题库」中查看和提交")
            st.session_state["problem_editor_seed"] = problem
            clear_cache()
        else:
            st.error(apply_result.error_text())
    col2.caption("导入后可以在「题库 → 题目详情」查看，也可以直接在「评测中心」提交解答。")


def _task_list() -> None:
    result = client().list_ai_tasks()
    if not result.ok:
        st.error(result.error_text())
        return
    tasks = result.data or []
    if not tasks:
        st.info("暂无命题任务。到「开始命题」提交一个需求试试。")
        return

    st.caption(f"共 {len(tasks)} 个任务（按创建时间倒序）。")
    options = [str(t["task_id"]) for t in tasks]
    labels = {
        str(t["task_id"]): f"{t.get('task_id')} · {STATUS_TEXT.get(t.get('status'), t.get('status'))}"
                           f" · {t.get('progress', '')[:40]}"
        for t in tasks
    }
    if st.session_state.get("ai_task_pick") not in options:
        st.session_state.pop("ai_task_pick", None)
    chosen = st.selectbox("选择任务", options, key="ai_task_pick",
                          format_func=lambda v: labels.get(v, v))
    col1, col2, col3 = st.columns([1, 1, 4])
    if col1.button("查看结果", key="task_view"):
        st.session_state["ai_task_show"] = chosen
    task = next((t for t in tasks if str(t["task_id"]) == chosen), {})
    if task.get("status") == "running" and col2.button("中断任务", key="task_cancel"):
        cancel = client().cancel_ai_task(chosen)
        if cancel.ok:
            st.success("任务已中断")
            st.rerun()
        else:
            st.error(cancel.error_text())
    if task.get("status") == "running":
        col3.caption("执行中的任务可以中断；中断会真正取消后台任务与进行中的模型请求。")

    st.dataframe(
        [{
            "任务": t.get("task_id"),
            "状态": STATUS_TEXT.get(t.get("status"), t.get("status")),
            "需求": (t.get("requirement") or "")[:40],
            "进度": (t.get("progress") or "")[:40],
            "创建时间": t.get("created_time"),
        } for t in tasks],
        hide_index=True,
    )
    show_id = st.session_state.get("ai_task_show")
    if show_id:
        st.divider()
        _show_result(str(show_id))
