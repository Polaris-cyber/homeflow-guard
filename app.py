from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from homeflow import __version__
from homeflow.compiler import CompilerError, OllamaClient, compile_request
from homeflow.evaluation import load_cases
from homeflow.exporter import ExportBlocked, export_yaml, validation_report_json
from homeflow.grounding import grounding_issues
from homeflow.io_utils import InputError, load_inventory, parse_inventory_bytes, parse_ir_text
from homeflow.models import AutomationIR, DeviceInventory, SimulationInput
from homeflow.simulator import simulate
from homeflow.validator import has_blocking_issues, validate_automation


ROOT = Path(__file__).resolve().parent
SAMPLE_INVENTORY_PATH = ROOT / "data" / "sample_home.yaml"
SAMPLE_STATES_PATH = ROOT / "data" / "sample_states.json"
CASES_PATH = ROOT / "data" / "gold_cases.jsonl"
DEMO_MODEL_CASES_PATH = ROOT / "data" / "demo_model_cases.json"
EVALUATION_PATH = ROOT / "artifacts" / "latest_evaluation.json"


st.set_page_config(page_title="HomeFlow Guard", page_icon="🏠", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f6f7f4; }
    .block-container { max-width: 1220px; padding-top: 2rem; padding-bottom: 4rem; }
    h1, h2, h3 { color: #18231f; }
    .hero { background: linear-gradient(135deg,#173f35,#2f6d5c); color:white; padding:1.5rem 1.7rem;
            border-radius:18px; margin-bottom:1rem; box-shadow:0 10px 30px rgba(20,60,50,.12); }
    .hero h1 { color:white; margin:0 0 .35rem 0; font-size:2rem; }
    .hero p { margin:0; color:#e4f2ed; }
    .step { color:#2f6d5c; font-weight:700; letter-spacing:.04em; font-size:.85rem; }
    .guard-card { background:white; border:1px solid #dce5e1; border-radius:14px; padding:1rem 1.1rem; }
    .muted { color:#65756f; font-size:.9rem; }
    div[data-testid="stMetric"] { background:white; border:1px solid #dce5e1; padding:.65rem; border-radius:12px; }
    </style>
    <div class="hero">
      <h1>HomeFlow Guard</h1>
      <p>把自然语言场景编译成可检查、可仿真、可导出的 Home Assistant 自动化。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def sample_inventory() -> DeviceInventory:
    return load_inventory(SAMPLE_INVENTORY_PATH)


@st.cache_data
def benchmark_cases() -> list[dict]:
    return load_cases(CASES_PATH)


@st.cache_data
def demo_model_cases() -> list[dict]:
    if not DEMO_MODEL_CASES_PATH.exists():
        return []
    return json.loads(DEMO_MODEL_CASES_PATH.read_text(encoding="utf-8"))


@st.cache_data
def sample_states() -> dict:
    return json.loads(SAMPLE_STATES_PATH.read_text(encoding="utf-8"))


def set_ir(ir: AutomationIR, source: str, run: dict | None = None, request_text: str | None = None) -> None:
    st.session_state["ir"] = ir
    st.session_state["ir_json"] = ir.model_dump_json(indent=2)
    st.session_state["ir_source"] = source
    st.session_state["model_run"] = run
    if request_text is not None:
        st.session_state["source_request"] = request_text
    st.session_state.pop("simulation", None)


def set_inventory(inventory: DeviceInventory) -> None:
    st.session_state["inventory"] = inventory
    st.session_state.pop("ir", None)
    st.session_state.pop("ir_json", None)
    st.session_state.pop("ir_source", None)
    st.session_state.pop("model_run", None)
    st.session_state.pop("source_request", None)
    st.session_state.pop("simulation", None)


if "inventory" not in st.session_state:
    st.session_state["inventory"] = sample_inventory()
if "states_json" not in st.session_state:
    st.session_state["states_json"] = json.dumps(sample_states(), ensure_ascii=False, indent=2)


with st.sidebar:
    st.markdown("### 运行模式")
    mode = st.radio(
        "选择模式",
        ["公开参考案例", "本地 Ollama"],
        help="公开模式不调用模型；本地模式将需求发送到你自己的 Ollama 服务。",
    )
    model = st.text_input("本地模型", value="qwen3:14b-q4_K_M", disabled=mode != "本地 Ollama")
    if mode == "本地 Ollama":
        client = OllamaClient()
        version = client.version()
        if version:
            st.success(f"Ollama 已连接 · {version}")
        else:
            st.warning("未连接 Ollama；规则编辑、校验和仿真仍可使用。")
    st.divider()
    st.caption("🔒 不连接真实设备，不保存上传内容，不接受 Token、密码或家庭地址。")
    st.caption("公开参考案例不是实时模型输出，不能作为模型效果证据。")
    st.caption(f"HomeFlow Guard v{__version__}")


device_tab, demand_tab, rule_tab, check_tab, export_tab = st.tabs(
    ["01 设备", "02 需求", "03 规则", "04 检查与仿真", "05 导出与评测"]
)


with device_tab:
    st.markdown('<div class="step">STEP 01 · DEVICE INVENTORY</div>', unsafe_allow_html=True)
    st.subheader("先限定 AI 能看见和使用的设备")
    left, right = st.columns([2, 1])
    with left:
        uploaded = st.file_uploader("上传脱敏后的 YAML / JSON 设备清单", type=["yaml", "yml", "json"])
        c1, c2 = st.columns(2)
        if c1.button("使用公开虚拟家庭", width="stretch"):
            set_inventory(sample_inventory())
            st.toast("已加载公开虚拟家庭")
        if uploaded and c2.button("校验并加载上传文件", width="stretch"):
            try:
                set_inventory(parse_inventory_bytes(uploaded.getvalue(), uploaded.name))
                st.success("设备清单已通过结构和敏感字段检查。")
            except InputError as exc:
                st.error(str(exc))
    inventory: DeviceInventory = st.session_state["inventory"]
    with right:
        st.markdown(
            f'<div class="guard-card"><b>{inventory.title}</b><br><span class="muted">'
            f'{len(inventory.devices)} 个实体 · 来源：{inventory.provenance}</span></div>',
            unsafe_allow_html=True,
        )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "实体": item.entity_id,
                    "区域": item.area,
                    "名称": item.display_name,
                    "能力": " / ".join(item.capabilities),
                    "敏感": item.sensitivity,
                }
                for item in inventory.devices
            ]
        ),
        hide_index=True,
        width="stretch",
        height=410,
    )


with demand_tab:
    st.markdown('<div class="step">STEP 02 · NATURAL LANGUAGE REQUIREMENT</div>', unsafe_allow_html=True)
    st.subheader("描述一个自动化目标")
    cases = benchmark_cases()
    frozen_cases = demo_model_cases()
    if frozen_cases:
        demo_cases = frozen_cases
    else:
        demo_cases = [item for item in cases if item["id"] in {"S01", "S04", "M01", "M05", "A02", "U04", "R02", "R06"}]
    labels = {f"{item['id']} · {item['user_request']}": item for item in demo_cases}
    selected_label = st.selectbox("参考案例", list(labels))
    selected_case = labels[selected_label]
    user_request = st.text_area(
        "需求描述",
        value=selected_case["user_request"],
        height=120,
        max_chars=2000,
        disabled=mode == "公开参考案例",
        help="本地模型模式可自由编辑；公开模式只能选择固化案例，不会实时理解修改后的文字。",
    )
    if mode == "公开参考案例" and frozen_cases:
        st.caption("以下是冻结前开发版的真实本地模型输出，仅用于交互演示；不是锁定测试集结果或实时模型调用。")
    if st.button("生成候选规则", type="primary", width="stretch"):
        if mode == "公开参考案例":
            if frozen_cases:
                set_ir(
                    AutomationIR.model_validate(selected_case["ir"]),
                    source="frozen_local_ollama_run",
                    run=selected_case["model_run"],
                    request_text=selected_case["user_request"],
                )
                st.info("已加载真实本地模型运行后固化的输出；输入为合成场景，当前不是实时调用。")
            else:
                set_ir(
                    AutomationIR.model_validate(selected_case["expected_ir"]),
                    source="synthetic_reference_fixture",
                    request_text=selected_case["user_request"],
                )
                st.info("已加载合成参考规则。它用于体验产品链路，不是实时 AI 结果。")
        else:
            try:
                with st.spinner("本地模型正在编译结构化规则……"):
                    result = compile_request(user_request, inventory, model=model)
                if result.ir:
                    set_ir(result.ir, source="ollama", run=result.run.model_dump(mode="json"), request_text=user_request)
                    if result.run.parse_status in {"normalized", "grounding_block"}:
                        st.warning("候选规则未通过澄清/证据约束；已丢弃动作，仅保留问题。不能导出 YAML。")
                    else:
                        st.success(f"结构化输出成功 · {result.run.latency_ms / 1000:.1f}s")
                else:
                    st.error(f"模型两次输出均未通过 schema：{result.run.error}")
                    st.code(result.raw_output or "<empty>", language="json")
            except CompilerError as exc:
                st.error(str(exc))
    st.markdown(
        "<span class='muted'>AI 只生成候选 AutomationIR；最终 YAML 由确定性程序编译。</span>",
        unsafe_allow_html=True,
    )


with rule_tab:
    st.markdown('<div class="step">STEP 03 · STRUCTURED RULE</div>', unsafe_allow_html=True)
    st.subheader("检查并编辑 AI 的候选规则")
    if "ir" not in st.session_state:
        st.info("请先在“需求”页生成或加载一条候选规则。")
    else:
        source = st.session_state.get("ir_source", "unknown")
        st.caption(f"规则来源：{source}")
        edited = st.text_area("AutomationIR JSON", value=st.session_state["ir_json"], height=500)
        if st.button("应用 JSON 修改"):
            try:
                parsed = parse_ir_text(edited)
                set_ir(parsed, source="manual_edit", run=st.session_state.get("model_run"))
                st.success("修改已通过 schema 校验。")
            except InputError as exc:
                st.error(str(exc))
        ir_value: AutomationIR = st.session_state["ir"]
        if ir_value.clarification_questions:
            st.warning("需要先澄清：\n\n" + "\n".join(f"- {q}" for q in ir_value.clarification_questions))
        c1, c2, c3 = st.columns(3)
        c1.metric("触发器", len(ir_value.triggers))
        c2.metric("条件", len(ir_value.conditions))
        c3.metric("动作", len(ir_value.actions))


with check_tab:
    st.markdown('<div class="step">STEP 04 · VALIDATE & SIMULATE</div>', unsafe_allow_html=True)
    st.subheader("先校验，再仿真")
    if "ir" not in st.session_state:
        st.info("尚无可检查的规则。")
    else:
        ir_value = st.session_state["ir"]
        issues = validate_automation(ir_value, inventory) + grounding_issues(
            ir_value, st.session_state.get("source_request", user_request), inventory
        )
        blocking = [issue for issue in issues if issue.severity.value == "blocking"]
        warnings = [issue for issue in issues if issue.severity.value == "warning"]
        c1, c2, c3 = st.columns(3)
        c1.metric("阻断问题", len(blocking))
        c2.metric("警告", len(warnings))
        c3.metric("可导出", "否" if blocking else "是")
        if not issues:
            st.success("未发现结构、能力或安全问题。")
        for issue in issues:
            message = f"{issue.code} · {issue.path} · {issue.message}"
            if issue.severity.value == "blocking":
                st.error(message)
            else:
                st.warning(message)
            if issue.requires_confirmation and issue.acknowledgement_key:
                if st.button("我理解风险并确认此敏感动作", key=f"ack-{issue.acknowledgement_key}"):
                    payload = ir_value.model_dump()
                    payload["risk_acknowledgements"] = sorted(
                        set(payload["risk_acknowledgements"]) | {issue.acknowledgement_key}
                    )
                    set_ir(AutomationIR.model_validate(payload), source="manual_confirmation", run=st.session_state.get("model_run"))
                    st.rerun()

        states_text = st.text_area("仿真初始状态 JSON", value=st.session_state["states_json"], height=260)
        if st.button("运行状态仿真", width="stretch"):
            try:
                states = json.loads(states_text)
                context = SimulationInput(states=states, manual=True, now_time="19:00:00", sun_event="sunset")
                if has_blocking_issues(issues):
                    st.error("仍有阻断问题，不能仿真可执行规则。")
                    st.stop()
                result = simulate(ir_value, inventory, context)
                st.session_state["simulation"] = result
                st.session_state["states_json"] = states_text
            except (json.JSONDecodeError, ValueError) as exc:
                st.error(f"初始状态无效：{exc}")
        if result := st.session_state.get("simulation"):
            st.write(f"**仿真结果：{result.status}**")
            st.dataframe(
                pd.DataFrame([step.model_dump(mode="json") for step in result.trace]),
                hide_index=True,
                width="stretch",
            )
            with st.expander("查看最终设备状态"):
                st.json({key: value.model_dump() for key, value in result.final_states.items()})


with export_tab:
    st.markdown('<div class="step">STEP 05 · EXPORT & EVALUATION</div>', unsafe_allow_html=True)
    st.subheader("导出可审查的配置和证据")
    if "ir" not in st.session_state:
        st.info("尚无可导出的规则。")
    else:
        ir_value = st.session_state["ir"]
        issues = validate_automation(ir_value, inventory) + grounding_issues(
            ir_value, st.session_state.get("source_request", user_request), inventory
        )
        if has_blocking_issues(issues):
            st.error("仍有阻断问题，YAML 下载已关闭。")
        else:
            try:
                yaml_content = export_yaml(ir_value, inventory)
                st.code(yaml_content, language="yaml")
                c1, c2 = st.columns(2)
                c1.download_button(
                    "下载 Home Assistant YAML",
                    yaml_content,
                    "homeflow-automation.yaml",
                    "text/yaml",
                    width="stretch",
                )
                c2.download_button(
                    "下载验证报告",
                    validation_report_json(issues),
                    "homeflow-validation.json",
                    "application/json",
                    width="stretch",
                )
            except ExportBlocked as exc:
                st.error(str(exc))
        if run := st.session_state.get("model_run"):
            with st.expander("本次模型运行记录"):
                st.json(run)

    st.divider()
    st.markdown("### 评测快照")
    if EVALUATION_PATH.exists():
        report = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
        if report.get("mode") == "fixture":
            st.warning("当前仅为参考 fixture 管线自检，不是模型成绩。")
        st.json(report)
    else:
        st.caption("尚未运行评测脚本。")

st.caption(
    "HomeFlow Guard v0.1 · 只生成候选配置，不控制真实设备。部署前请在隔离的 Home Assistant 环境复核。"
)
