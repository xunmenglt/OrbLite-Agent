import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
from queue import Queue, Empty
from pathlib import Path
import threading
import time
import streamlit as st
from pydantic import PrivateAttr

from orblite.config import config
from orblite.printer.base import Printer
from orblite.schemas.agent_req import AgentRequest
from orblite.schemas.base import AgentType
from orblite.schemas.context import AgentContext
from orblite.schemas.file import File
from orblite.service.plan_solve_handler import PlanSolveHandler
from orblite.tool.base import BaseTool
from orblite.tool.common.file_tool import FileTool
from orblite.tool.mcp.mcp_tool import MCPTool
from orblite.tool.tool_collection import ToolCollection
from orblite.utils.secrets import generate_random_id


@dataclass
class StreamlitEvent:
    message_type: str
    message: object
    message_id: str | None = None
    is_final: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TimelineStep:
    index: int
    title: str
    detail: str
    status: str


def _format_event_time(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
    except Exception:
        return timestamp


def _format_json_block(message: object) -> str:
    try:
        payload = json.dumps(message, ensure_ascii=False, indent=2)
    except Exception:
        payload = str(message)
    return f"<pre class=\"event-json\">{payload}</pre>"


def _format_plan_html(plan_data: dict) -> str:
    title = plan_data.get("title") or ""
    steps = plan_data.get("steps") or []
    statuses = plan_data.get("step_status") or []
    blocks = []
    if title:
        blocks.append(f"<div class=\"event-text\"><strong>计划：</strong>{title}</div>")
    if steps:
        blocks.append("<ul class=\"event-plan\">")
        for idx, step in enumerate(steps):
            status_value = statuses[idx] if idx < len(statuses) else "not_started"
            status_label = {
                "not_started": "待开始",
                "in_progress": "进行中",
                "completed": "已完成",
                "blocked": "阻塞",
            }.get(status_value, "待开始")
            blocks.append(
                f"<li><span class=\"plan-step\">{idx + 1}. {step}</span>"
                f"<span class=\"plan-status\">{status_label}</span></li>"
            )
        blocks.append("</ul>")
    return "".join(blocks) if blocks else "<div class=\"event-text\">暂无计划</div>"


def _format_collapsible(title: str, content: object, expanded: bool = False, preview_chars: int | None = None) -> str:
    if content is None:
        return ""
    if isinstance(content, (dict, list)):
        content_str = json.dumps(content, ensure_ascii=False, indent=2)
    else:
        content_str = str(content)
    preview = content_str
    if preview_chars is not None and len(content_str) > preview_chars:
        preview = content_str[:preview_chars] + "..."
    open_attr = " open" if expanded else ""
    preview_block = (
        f"<div class=\"event-collapse-preview\">{preview}</div>" if preview_chars is not None else ""
    )
    return (
        f"<details class=\"event-collapse\"{open_attr}>"
        f"<summary>{title}</summary>"
        f"{preview_block}"
        f"<pre class=\"event-json\">{content_str}</pre>"
        "</details>"
    )


def _format_result_html(message: object) -> str:
    if not isinstance(message, dict):
        return _format_json_block(message)
    task_summary = message.get("taskSummary") or ""
    file_list = message.get("fileList") or []
    summary_html = ""
    if task_summary:
        formatted = str(task_summary).replace("\n", "<br>")
        summary_html = f"<div class=\"event-text\">{formatted}</div>"
    files_html = ""
    if file_list:
        items = []
        for item in file_list:
            if isinstance(item, dict):
                file_name = item.get("file_name") or item.get("fileName") or "未命名文件"
                description = item.get("description") or ""
            else:
                file_name = getattr(item, "file_name", None) or "未命名文件"
                description = getattr(item, "description", "")
            label = f"<strong>{file_name}</strong>"
            if description:
                label = f"{label}<div class=\"event-text\">{description}</div>"
            items.append(f"<li>{label}</li>")
        files_html = f"<div class=\"event-text\"><strong>产出文件</strong></div><ul class=\"event-plan\">{''.join(items)}</ul>"
    return summary_html + files_html


class StreamlitPrinter(Printer):
    _event_queue: Queue = PrivateAttr()

    def __init__(self, event_queue: Queue):
        super().__init__()
        self._event_queue = event_queue

    async def send(
        self,
        message_id: str | None = None,
        message_type: str = "",
        message: object = None,
        is_final: bool = False,
    ) -> None:
        self._event_queue.put(
            StreamlitEvent(
                message_type=message_type,
                message=message,
                message_id=message_id,
                is_final=is_final,
            )
        )

    async def close(self) -> None:
        self._event_queue.put(
            StreamlitEvent(message_type="close", message="连接已关闭", is_final=True)
        )

    async def update_agent_type(self, agent_type: AgentType) -> None:
        self.agent_type = agent_type
        self._event_queue.put(
            StreamlitEvent(
                message_type="agent_type",
                message={"agentType": agent_type.value},
            )
        )


async def _init_mcp_tools() -> list[BaseTool]:
    total_tools: list[BaseTool] = []
    for mcp_item in config.mcp_config.servers.values():
        client = MCPTool(
            name=mcp_item.name,
            description=mcp_item.description,
            server_url=mcp_item.url,
            req_headers=mcp_item.headers,
        )
        tools = await client.list_tool()
        total_tools.extend(tools)
    return total_tools


async def _init_tool_collection() -> ToolCollection:
    tool_collection = ToolCollection()
    tools = await _init_mcp_tools()
    for tool in tools:
        tool_collection.add_tool(tool)
    return tool_collection


async def run_orblite_stream(query: str, event_queue: Queue, request_id: str) -> None:
    tool_collection = await _init_tool_collection()
    printer = StreamlitPrinter(event_queue)
    request = AgentRequest(
        request_id=request_id,
        agent_type=AgentType.PLAN_SOLVE,
        query=query,
        sop_prompt="",
    )
    agent_context = AgentContext(
        request_id=request_id,
        session_id=request_id,
        printer=printer,
        query=request.query,
        task="",
        date_info=datetime.now().isoformat(),
        sop_prompt="",
        agent_type=request.agent_type,
        is_stream=request.is_stream,
    )
    file_tool = FileTool(agent_context=agent_context)
    tool_collection.add_tool(file_tool)
    agent_context.tool_collection = tool_collection
    handler = PlanSolveHandler()
    await handler.handle(agent_context, request)
    event_queue.put(StreamlitEvent(message_type="run_complete", message={"status": "done"}))


def _start_background_run(prompt: str) -> None:
    event_queue: Queue = Queue()
    request_id = generate_random_id()
    st.session_state.event_queue = event_queue
    st.session_state.events = st.session_state.events or []
    st.session_state.current_step = None
    st.session_state.current_plan = None
    st.session_state.request_id = request_id
    st.session_state.running = True

    def _runner() -> None:
        asyncio.run(run_orblite_stream(prompt, event_queue, request_id))

    thread = threading.Thread(target=_runner, daemon=True)
    st.session_state.run_thread = thread
    thread.start()


def _drain_events() -> None:
    event_queue: Queue | None = st.session_state.get("event_queue")
    if not event_queue:
        return
    while True:
        try:
            event = event_queue.get_nowait()
        except Empty:
            break
        st.session_state.events.append(event)
        
        if event.message_type == "step_start":
            st.session_state.current_step = event.message
        if event.message_type in {"plan_ready", "plan_updated", "plan"}:
            st.session_state.current_plan = event.message
        if event.message_type == "product_files":
            st.session_state.current_files = event.message
            
        if event.message_type == "result":
            if isinstance(event.message, dict):
                task_summary = event.message.get("taskSummary", "")
                file_list = event.message.get("fileList", [])
                
                md_parts = []
                if task_summary:
                    md_parts.append(str(task_summary))
                    
                if file_list:
                    md_parts.append("#### 📂 产出文件")
                    for f in file_list:
                        if isinstance(f, dict):
                            fname = f.get("file_name") or f.get("fileName") or "未命名文件"
                            fdesc = f.get("description", "")
                        else:
                            fname = getattr(f, "file_name", None) or "未命名文件"
                            fdesc = getattr(f, "description", "")
                        
                        if fdesc:
                            md_parts.append(f"- **{fname}**: {fdesc}")
                        else:
                            md_parts.append(f"- **{fname}**")
                
                if md_parts:
                    final_reply = "\n\n".join(md_parts)
                    st.session_state.messages.append({"role": "assistant", "content": final_reply})

        if event.is_final or event.message_type in {"session_end", "run_complete"}:
            st.session_state.running = False


st.set_page_config(page_title="OrbLiteAgent 客户端", layout="wide")

if "events" not in st.session_state:
    st.session_state.events = []
if "messages" not in st.session_state:
    st.session_state.messages = []
if "running" not in st.session_state:
    st.session_state.running = False
if "event_queue" not in st.session_state:
    st.session_state.event_queue = None
if "current_step" not in st.session_state:
    st.session_state.current_step = None
if "current_plan" not in st.session_state:
    st.session_state.current_plan = None
if "current_files" not in st.session_state:
    st.session_state.current_files = []
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None
if "selected_file_content" not in st.session_state:
    st.session_state.selected_file_content = None
if "request_id" not in st.session_state:
    st.session_state.request_id = None

st.markdown(
    """
<style>
/* 1. 锁死全局与最外层容器的滚动和高度 */
.stApp, html, body {
    overflow: hidden !important;
    height: 100vh !important;
    margin: 0 !important;
}
div[data-testid="stExpanderDetails"] {
    max-height: 50vh !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
}
/* 美化展开框自己的滚动条 */
div[data-testid="stExpanderDetails"]::-webkit-scrollbar {
    width: 6px;
}
div[data-testid="stExpanderDetails"]::-webkit-scrollbar-thumb {
    background-color: #cbd5e1;
    border-radius: 4px;
}
.block-container {
    max-width: 100% !important;
    padding: 1.5rem 2rem 0 2rem !important; /* 只保留上、左右边距 */
    height: 100vh !important;
    overflow: hidden !important; 
}

/* 2. 核心修复：锁死 Streamlit 的“行（Row）”容器高度 */
/* 这一步防止了整个行被内容撑出屏幕 */
div[data-testid="stHorizontalBlock"] {
    height: calc(100vh - 2rem) !important;
    /* 改为 stretch，强制列高跟随外层容器，真正激活滚动 */
    align-items: stretch !important; 
}

/* 3. 强制让列（Column）占满行的高度，并在溢出时滚动 */
div[data-testid="column"] {
    height: 100% !important;
    max-height: 100% !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    padding-right: 0.8rem;
    /* 关键：给底部留出 150px 的超大空白，确保最后一行字不会被输入框遮挡 */
    padding-bottom: 150px !important; 
}

/* 定制滚动条，使其更优雅 */
div[data-testid="column"]::-webkit-scrollbar {
    width: 6px;
}
div[data-testid="column"]::-webkit-scrollbar-thumb {
    background-color: #cbd5e1;
    border-radius: 4px;
}
div[data-testid="column"]::-webkit-scrollbar-track {
    background: transparent;
}

/* 隐藏 Streamlit 默认的底部空白 Footer */
footer {
    display: none !important;
}

/* ================= 以下为 UI 组件样式（保持原样） ================= */
[data-testid="stSidebarHeader"] { display: none !important; }
section[data-testid="stSidebar"] { width: 320px !important; }
section[data-testid="stSidebar"] > div { padding-top: 1.5rem !important; }
.brand-logo { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem; color: #ffffff; background: linear-gradient(135deg, #4f46e5, #06b6d4); box-shadow: 0 6px 12px rgba(79, 70, 229, 0.2); flex-shrink: 0; }
.brand-text { display: flex; flex-direction: column; }
.brand-title { font-size: 0.9rem; font-weight: 700; color: #111827; margin-bottom: 0.1rem; line-height: 1.2; }
.brand-subtitle { font-size: 0.75rem; color: #6b7280; line-height: 1.2; }
.chat-bubble { background: #f7f7f9; border: 1px solid #ececf3; padding: 0.7rem 0.85rem; border-radius: 12px; line-height: 1.5; font-size: 0.88rem; }
.chat-bubble p:last-child { margin-bottom: 0; }
.chat-bubble ul { margin-bottom: 0; padding-left: 1.2rem; }
.input-dock { position: fixed; left: 320px; right: 0; bottom: 0; padding: 0.8rem 2rem 1rem; background: #ffffff; border-top: 1px solid #ececf3; z-index: 1000; }
.input-dock .stChatInput { max-width: 100%; margin: 0; }
.status-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.status-pill { background: #f3f4f6; color: #111827; border: 1px solid #e5e7eb; padding: 0.25rem 0.6rem; border-radius: 999px; font-size: 0.75rem; }
.status-pill.active { background: #eef2ff; color: #4338ca; border-color: #c7d2fe; }
.section-title { display: flex; align-items: center; justify-content: space-between; font-weight: 600; font-size: 0.95rem; margin: 1rem 0 0.5rem; }
.section-title span { color: #9ca3af; font-size: 0.75rem; }
.event-scroll { display: flex; flex-direction: column; gap: 0.6rem; height: auto; min-height: min-content; }
.event-card { border: 1px solid #ececf3; background: #ffffff; border-radius: 10px; padding: 0.65rem 0.85rem; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.03); }
.event-card.event-step { border-left: 3px solid #3b82f6; background: #f8fafc; }
.event-card.event-success { border-left: 3px solid #22c55e; }
.event-card.event-error { border-left: 3px solid #ef4444; background: #fef2f2; }
.event-title { font-weight: 600; font-size: 0.88rem; margin-bottom: 0.2rem; }
.event-time { font-size: 0.72rem; color: #94a3b8; margin-bottom: 0.4rem; }
.event-step-body { background: #eef2ff; border-radius: 8px; padding: 0.5rem 0.7rem; color: #1e293b; font-size: 0.85rem; line-height: 1.4; }
.event-text { font-size: 0.85rem; color: #1f2937; line-height: 1.4; }
.event-block { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.5rem 0.7rem; font-size: 0.8rem; color: #1f2937; white-space: pre-wrap; margin-top: 0.4rem; }
.event-collapse { border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.4rem 0.6rem; margin-top: 0.4rem; background: #f8fafc; }
.event-collapse summary { cursor: pointer; font-weight: 600; color: #1f2937; font-size: 0.85rem; }
.event-collapse-preview { margin-top: 0.25rem; font-size: 0.78rem; color: #475569; }
.event-collapse-content { margin-top: 0.3rem; font-size: 0.8rem; color: #111827; white-space: pre-wrap; }
.event-plan { list-style: none; padding-left: 0; margin: 0.35rem 0 0; }
.event-plan li { display: flex; justify-content: space-between; gap: 0.75rem; padding: 0.25rem 0; border-bottom: 1px dashed #e5e7eb; font-size: 0.85rem; }
.event-plan li:last-child { border-bottom: none; }
.plan-step { color: #111827; font-weight: 500; }
.plan-status { font-size: 0.72rem; color: #6b7280; }
.task-item { display: flex; gap: 0.6rem; padding: 0.5rem 0.6rem; border-radius: 10px; border: 1px solid #e5e7eb; background: #ffffff; margin-bottom: 0.4rem; box-shadow: 0 4px 10px rgba(15, 23, 42, 0.03); }
.task-index { width: 24px; height: 24px; border-radius: 6px; background: #eef2ff; color: #4338ca; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.8rem; }
.task-main { flex: 1; }
.task-title { font-size: 0.82rem; color: #111827; font-weight: 600; line-height: 1.3; }
.task-status { margin-top: 0.25rem; display: inline-flex; align-items: center; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.7rem; font-weight: 600; border: 1px solid transparent; }
.task-status.pending { background: #f3f4f6; color: #6b7280; border-color: #e5e7eb; }
.task-status.active { background: #eef2ff; color: #4338ca; border-color: #c7d2fe; }
.task-status.done { background: #ecfdf3; color: #15803d; border-color: #bbf7d0; }
.task-status.blocked { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.event-json { background: #0f172a; color: #e2e8f0; border-radius: 8px; padding: 0.5rem 0.65rem; font-size: 0.78rem; overflow-x: auto; }
div[data-testid="stHeader"] { background: transparent; }
div[data-testid="stToolbar"] { visibility: hidden; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
.workspace-card { border: 1px solid #e5e7eb; border-radius: 10px; background: #ffffff; overflow: hidden; }
.workspace-header { padding: 0.8rem 1rem; border-bottom: 1px solid #e5e7eb; background: #f8fafc; font-weight: 600; color: #111827; font-size: 0.9rem; }
.workspace-empty { padding: 3rem 1rem; text-align: center; color: #94a3b8; font-size: 0.9rem; background: #ffffff; }
.brand-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem; }
#column-scroll-anchor { height: 1px; margin-top: 10px; }
</style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
        <div class="brand-header">
            <div class="brand-logo">ORB</div>
            <div class="brand-text">
                <div class="brand-title">OrbLiteAgent 客户端</div>
                <div class="brand-subtitle">轻量级智能体</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.header("会话设置")
    st.caption("输入需求后启动一次任务，可在结果区查看执行过程与详情。")
    running_label = "执行中" if st.session_state.running else "空闲"
    status_class = "status-pill active" if st.session_state.running else "status-pill"
    st.markdown(
        f"<div class=\"status-row\"><div class=\"{status_class}\">状态：{running_label}</div></div>",
        unsafe_allow_html=True,
    )
    if st.session_state.running:
        st.markdown("### 当前执行步骤")
        current_step = st.session_state.current_step
        if current_step:
            st.info(
                f"步骤 {current_step.get('stepIndex')}：{current_step.get('task', '')}"
            )
        else:
            st.info("正在规划中...")

    st.markdown("### 任务列表")
    current_plan = st.session_state.current_plan
    plan_data = current_plan.get("plan") if isinstance(current_plan, dict) else None
    if isinstance(plan_data, dict):
        title = plan_data.get("title") or ""
        steps_data = plan_data.get("steps") or []
        statuses = plan_data.get("step_status") or []
        if title:
            st.caption(f"任务：{title}")
        if steps_data:
            for idx, step_title in enumerate(steps_data, start=1):
                status_value = statuses[idx - 1] if idx - 1 < len(statuses) else "not_started"
                status_label = {
                    "not_started": "待开始",
                    "in_progress": "进行中",
                    "completed": "已完成",
                    "blocked": "阻塞",
                }.get(status_value, "待开始")
                status_class = {
                    "not_started": "task-status pending",
                    "in_progress": "task-status active",
                    "completed": "task-status done",
                    "blocked": "task-status blocked",
                }.get(status_value, "task-status pending")
                st.markdown(
                    f"<div class=\"task-item\"><div class=\"task-index\">{idx}</div><div class=\"task-main\"><div class=\"task-title\">{step_title}</div><div class=\"{status_class}\">{status_label}</div></div></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("正在规划中...")
    else:
        st.info("暂无计划")

conversation_col, file_col = st.columns([2.0, 1.8], gap="large")

with conversation_col:
    # 渲染对话
    st.markdown("<div class=\"section-title\">对话<span>Conversation</span></div>", unsafe_allow_html=True)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(f"<div class=\"chat-bubble\">\n\n{msg['content']}\n\n</div>", unsafe_allow_html=True)
            
    # 使用 expander 包裹执行详情
    with st.expander("🛠️ 查看执行过程详情", expanded=st.session_state.running):
        event_cards = []
        
        if not st.session_state.events:
            st.info("暂无执行记录")
        else:
            tool_start_map: dict[str, dict] = {}
            for event in st.session_state.events:
                event_kind = event.message_type
                time_text = _format_event_time(event.timestamp)
                if event_kind in {"planning_start", "plan_ready", "plan_updated", "plan"}:
                    plan_content = ""
                    if isinstance(event.message, dict):
                        plan_data = event.message.get("plan")
                        if isinstance(plan_data, dict):
                            plan_content = _format_plan_html(plan_data)
                        else:
                            plan_content = _format_json_block(event.message)
                    elif isinstance(event.message, list):
                        plan_content = _format_json_block(event.message)
                    else:
                        plan_content = f"<div class=\"event-text\">{event.message}</div>"
                    event_cards.append(
                        f"<div class=\"event-card\"><div class=\"event-title\">规划更新</div><div class=\"event-time\">{time_text}</div>{plan_content}</div>"
                    )
                elif event_kind == "step_start":
                    step_index = ""
                    task_text = ""
                    if isinstance(event.message, dict):
                        step_index = event.message.get("stepIndex", "")
                        task_text = event.message.get("task", "")
                    event_cards.append(
                        f"<div class=\"event-card event-step\"><div class=\"event-title\">开始执行步骤 {step_index}</div><div class=\"event-time\">{time_text}</div><div class=\"event-step-body\">{task_text}</div></div>"
                    )
                elif event_kind == "tool_thought":
                    event_cards.append(
                        f"<div class=\"event-card\"><div class=\"event-title\">工具调用思路</div><div class=\"event-time\">{time_text}</div><div class=\"event-text\">{event.message}</div></div>"
                    )
                elif event_kind == "tool_start":
                    if isinstance(event.message, dict):
                        tool_key = f"{event.message.get('toolName')}|{event.message.get('toolParam')}"
                        tool_start_map[tool_key] = event.message
                    else:
                        event_cards.append(
                            f"<div class=\"event-card\"><div class=\"event-title\">工具执行中</div><div class=\"event-time\">{time_text}</div><div class=\"event-text\">{event.message}</div></div>"
                        )
                elif event_kind == "tool_result":
                    tool_info = event.message if isinstance(event.message, dict) else {}
                    tool_key = f"{tool_info.get('toolName')}|{tool_info.get('toolParam')}"
                    start_info = tool_start_map.pop(tool_key, None)
                    tool_name = tool_info.get("toolName") or (start_info or {}).get("toolName") or "工具"
                    tool_param = (start_info or {}).get("toolParam") or tool_info.get("toolParam")
                    tool_result = tool_info.get("toolResult") if isinstance(tool_info, dict) else None
                    param_block = _format_collapsible("参数", tool_param)
                    result_block = _format_collapsible("结果", tool_result, expanded=False, preview_chars=200)
                    event_cards.append(
                        f"<div class=\"event-card\"><div class=\"event-title\">工具执行：{tool_name}</div><div class=\"event-time\">{time_text}</div>{param_block}{result_block}</div>"
                    )
                elif event_kind == "task_summary":
                    event_cards.append(
                        f"<div class=\"event-card\"><div class=\"event-title\">任务总结</div><div class=\"event-time\">{time_text}</div>{_format_json_block(event.message)}</div>"
                    )
                elif event_kind == "result":
                    event_cards.append(
                        f"<div class=\"event-card\"><div class=\"event-title\">最终结果</div><div class=\"event-time\">{time_text}</div>{_format_result_html(event.message)}</div>"
                    )
                elif event_kind == "error":
                    event_cards.append(
                        f"<div class=\"event-card event-error\"><div class=\"event-title\">执行异常</div><div class=\"event-time\">{time_text}</div><div class=\"event-text\">{event.message}</div></div>"
                    )
                elif event_kind == "session_end":
                    event_cards.append(
                        f"<div class=\"event-card event-success\"><div class=\"event-title\">任务结束</div><div class=\"event-time\">{time_text}</div></div>"
                    )
                else:
                    event_cards.append(
                        f"<div class=\"event-card\"><div class=\"event-title\">{event_kind}</div><div class=\"event-time\">{time_text}</div>{_format_json_block(event.message)}</div>"
                    )

        if event_cards:
            st.markdown(
                f"<div class=\"event-scroll\">{''.join(event_cards)}</div>",
                unsafe_allow_html=True,
            )

    # 放置在整个左边列最后面的锚点，用于自动滚动
    st.markdown('<div id="column-scroll-anchor"></div>', unsafe_allow_html=True)
    event_count = len(st.session_state.events) if st.session_state.events else 0
    st.components.v1.html(
        f"""
        <script>
        const currentEventCount = {event_count};
        const parentWin = window.parent;
        const parentDoc = window.parent.document;

        // 核心拦截逻辑：只有当 Python 端传来的事件数量增加了，才执行滚动逻辑
        if (parentWin._orb_last_event_count !== currentEventCount) {{
            const cols = parentDoc.querySelectorAll('div[data-testid="column"]');
            if (cols.length > 0) {{
                const targetCol = cols[0];
                const distanceFromBottom = targetCol.scrollHeight - targetCol.scrollTop - targetCol.clientHeight;
                
                // 智能判断：如果用户正停留在底部附近（容差 150px），或者刚开始执行，才自动滚到底部
                if (distanceFromBottom < 150 || currentEventCount <= 5) {{
                    targetCol.scrollTo({{
                        top: targetCol.scrollHeight,
                        behavior: 'smooth'
                    }});
                }}
            }}
            // 更新前端的记录值
            parentWin._orb_last_event_count = currentEventCount;
        }}
        </script>
        """,
        height=0,
        width=0
    )

with file_col:
    raw_files = st.session_state.current_files or []
    files: list[File] = []
    for item in raw_files:
        if isinstance(item, File):
            files.append(item)
        elif isinstance(item, dict):
            try:
                files.append(File(**item))
            except Exception:
                continue
                
    if not files:
        st.markdown(
            """
            <div class="workspace-card" style="margin-top: 0.8rem;">
                <div class="workspace-header">工作空间</div>
                <div class="workspace-empty">暂无文件</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div class="workspace-card" style="margin-top: 0.8rem; margin-bottom: 0.8rem;">
                <div class="workspace-header" style="border-bottom: none;">工作空间</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        options = []
        option_map: dict[str, File] = {}
        for file_item in files:
            file_label = file_item.file_name or "未命名文件"
            if file_item.description:
                file_label = f"{file_label} - {file_item.description}"
            options.append(file_label)
            option_map[file_label] = file_item
            
        selected_label = st.selectbox("选择文件查看", options, index=0, key="file_select", label_visibility="collapsed")
        selected_file = option_map.get(selected_label)
        st.session_state.selected_file = selected_file

        if selected_file:                
            request_id = st.session_state.request_id
            if request_id and selected_file.file_name:
                file_path = Path(config.root_path) / "file_tmp_dir" / request_id / selected_file.file_name
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    st.session_state.selected_file_content = content
                else:
                    st.session_state.selected_file_content = None

            if st.session_state.selected_file_content:
                st.markdown("<div style='margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e5e7eb;'>", unsafe_allow_html=True)
                file_name = selected_file.file_name or ""
                
                if file_name.lower().endswith(".html"):
                    st.components.v1.html(st.session_state.selected_file_content, height=600, scrolling=True)
                elif file_name.lower().endswith(".md"):
                    st.markdown(st.session_state.selected_file_content)
                else:
                    st.code(st.session_state.selected_file_content)
                st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class=\"input-dock\">", unsafe_allow_html=True)
prompt = st.chat_input("请输入任务")
st.markdown("</div>", unsafe_allow_html=True)

if prompt and not st.session_state.running:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(f"<div class=\"chat-bubble\">\n\n{prompt}\n\n</div>", unsafe_allow_html=True)
    _start_background_run(prompt)
    st.rerun()

if st.session_state.running:
    _drain_events()
else:
    _drain_events()

if st.session_state.running:
    # 使用静态提示代替 spinner 动画，防止频繁重绘打断用户的鼠标滚动
    st.markdown("<div style='color:#6b7280; text-align:center; padding: 1rem; font-size: 0.9rem;'>⏳ 智能体正在执行，请稍候...</div>", unsafe_allow_html=True)
    time.sleep(0.4)
    st.rerun()
