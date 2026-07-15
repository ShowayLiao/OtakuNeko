import operator
from typing import AsyncGenerator, Dict, Any, List, Optional, Annotated, TypedDict, TYPE_CHECKING
from langchain_core.messages import BaseMessage, trim_messages, filter_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agents.registry import ToolRegistry
from app.agents.tools import ALL_TOOLS
from app.core.logging import get_logger
import time

if TYPE_CHECKING:
    from app.memory.manager import MemoryManager

logger = get_logger(__name__)


class CodingAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    reasoning_trace: str
    current_dir: str
    plan: str
    completed_steps: Annotated[List[str], operator.add]
    last_terminal_output: str


THINK_SYSTEM_PROMPT = """你是一个内部推理引擎。请逐步分析用户的问题：
1. 理解用户意图
2. 确定需要什么信息
3. 调用工具搜索/获取数据
4. 对获取的数据进行分析和筛选

注意：你只需要分析和推理，不需要给出最终回复。不要对用户说话。"""

SPEAK_SYSTEM_PROMPT = """你是一个友好的二次元助手。基于前面的分析结果，
用自然、亲切的语言回答用户的问题。不要再调用工具。"""


class ChatWorkflow:
    def __init__(self, api_key: str, base_url: str,
                 memory_manager: Optional["MemoryManager"] = None,
                 db_path: str = "data/checkpoints.db",
                 store=None,
                 registry: Optional[ToolRegistry] = None,
                 enable_interrupt: bool = False):
        self.api_key = api_key
        self.base_url = base_url
        self.memory = memory_manager
        self._db_path = db_path
        self._store = store
        self.registry = registry or ToolRegistry()
        if not registry:
            self.registry.register_all(ALL_TOOLS)
        self.checkpointer = None
        self.app = None
        self._speak_prompt: Optional[str] = None
        self._enable_interrupt = enable_interrupt

    def _get_tools(self):
        return self.registry.get_all()

    async def _ensure_checkpointer(self):
        if self.checkpointer is None:
            import aiosqlite
            conn = await aiosqlite.connect(self._db_path)
            self.checkpointer = AsyncSqliteSaver(conn)
            self.app = self._compile_graph()

    def _compile_graph(self):
        workflow = StateGraph(CodingAgentState)
        workflow.add_node("think", self._think_node)
        workflow.add_node("speak", self._speak_node)
        workflow.add_node("tools", ToolNode(self._get_tools()))

        workflow.add_edge(START, "think")
        workflow.add_conditional_edges("think", self._think_condition, {
            "tools": "tools",
            "speak": "speak",
        })
        workflow.add_edge("tools", "think")
        workflow.add_edge("speak", END)

        compile_kwargs = {"checkpointer": self.checkpointer, "store": self._store}
        if self._enable_interrupt:
            compile_kwargs["interrupt_before"] = ["speak"]

        return workflow.compile(**compile_kwargs)

    def _think_condition(self, state: CodingAgentState) -> str:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "speak"

    @staticmethod
    def _strip_orphaned_tool_calls(messages):
        tool_result_ids = set()
        for m in messages:
            if hasattr(m, "tool_call_id"):
                tool_result_ids.add(m.tool_call_id)

        cleaned = []
        for m in messages:
            if hasattr(m, "tool_calls") and m.tool_calls:
                orphaned = [
                    tc for tc in m.tool_calls
                    if tc.get("id") not in tool_result_ids
                ]
                if orphaned:
                    continue
            cleaned.append(m)
        return cleaned

    def _trim_and_clean(self, messages):
        messages = filter_messages(messages, include_types=["human", "ai", "system", "tool"])

        try:
            messages = trim_messages(
                messages,
                max_tokens=8000,
                strategy="last",
                token_counter=self.llm,
                include_system=True,
                start_on="human",
            )
        except Exception:
            pass

        return self._strip_orphaned_tool_calls(messages)

    async def _think_node(self, state: CodingAgentState):
        messages = list(state["messages"])
        messages = self._trim_and_clean(messages)

        think_sys = {"role": "system", "content": THINK_SYSTEM_PROMPT}
        messages.insert(0, think_sys)

        logger.info("think_node", extra={
            "thread_id": state.get("_thread_id", "unknown"),
            "message_count": len(messages),
        })

        response = await self.llm_with_tools.ainvoke(messages)
        return {
            "messages": [response],
            "reasoning_trace": response.content if hasattr(response, "content") else "",
        }

    async def _speak_node(self, state: CodingAgentState):
        messages = list(state["messages"])
        messages = self._trim_and_clean(messages)

        speak_sys = {"role": "system", "content": self._speak_prompt or SPEAK_SYSTEM_PROMPT}
        messages.insert(0, speak_sys)

        logger.info("speak_node", extra={
            "thread_id": state.get("_thread_id", "unknown"),
            "message_count": len(messages),
        })

        response = await self.llm.ainvoke(messages)
        return {"messages": [response]}

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        thread_id: str = "default",
        speak_prompt: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        await self._ensure_checkpointer()
        self._speak_prompt = speak_prompt
        self.llm = ChatOpenAI(
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
            streaming=True
        )
        self.llm_with_tools = self.llm.bind_tools(self._get_tools())

        enriched_messages = list(messages)
        if self.memory and thread_id:
            user_query = next((m["content"] for m in reversed(messages)
                              if m.get("role") == "user"), "")
            if user_query:
                ctx = await self.memory.load_context(thread_id, user_query)
                if ctx.summary:
                    enriched_messages.insert(0, {"role": "system", "content": ctx.summary})

        config = {"configurable": {"thread_id": thread_id}}

        tool_count: int = 0
        tool_start_times: Dict[str, float] = {}
        _thinking_active: bool = False
        _message_started: bool = False
        _last_reasoning: str = ""

        def _emit(event_type: str, **kwargs) -> Dict[str, Any]:
            return {"type": event_type, **kwargs}

        try:
            async for event in self.app.astream_events({
                "messages": enriched_messages,
                "current_dir": "",
                "plan": "",
                "completed_steps": [],
                "last_terminal_output": "",
                "reasoning_trace": "",
            }, config=config, version="v2"):
                kind = event["event"]
                node_name = event.get("metadata", {}).get("langgraph_node")

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]

                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        for tc in chunk.tool_call_chunks:
                            if tc.get("name"):
                                yield _emit("tool_call_delta",
                                            id=tc.get("id"), name=tc.get("name"),
                                            delta=tc.get("args", ""))
                        continue

                    if not (hasattr(chunk, "content") and isinstance(chunk.content, str)
                            and chunk.content):
                        continue

                    delta = chunk.content

                    if node_name == "think":
                        if not _thinking_active:
                            _thinking_active = True
                            _last_reasoning = ""
                            yield _emit("thinking_start")
                        _last_reasoning += delta
                        yield _emit("thinking_chunk", content=delta)

                    elif node_name == "speak":
                        if _thinking_active:
                            _thinking_active = False
                            yield _emit("thinking_end")
                        if not _message_started:
                            _message_started = True
                            yield _emit("message_start")
                        yield _emit("message_chunk", content=delta)

                elif kind == "on_chat_model_end":
                    if node_name == "think":
                        if _thinking_active:
                            yield _emit("thinking_end")
                            _thinking_active = False
                        if _last_reasoning:
                            yield _emit("reasoning_trace", content=_last_reasoning)
                    elif node_name == "speak" and _message_started:
                        yield _emit("message_end")
                        _message_started = False

                elif kind == "on_tool_start":
                    if _thinking_active:
                        yield _emit("thinking_end")
                        _thinking_active = False
                    _message_started = False
                    tool_name = event["name"]
                    run_id = event["run_id"]
                    inputs = event["data"].get("input", {})
                    tool_start_times[run_id] = time.perf_counter()
                    yield _emit("tool_call_start", name=tool_name, inputs=inputs)

                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    run_id = event["run_id"]
                    duration_ms = 0.0
                    if run_id in tool_start_times:
                        duration_ms = (
                            time.perf_counter() - tool_start_times.pop(run_id)
                        ) * 1000

                    raw_output = event["data"].get("output")
                    tool_count += 1

                    if hasattr(raw_output, "content"):
                        output_data = raw_output.content
                    elif isinstance(raw_output, (dict, list, str, int, float, bool,
                                                 type(None))):
                        output_data = raw_output
                    else:
                        output_data = str(raw_output)

                    tool_status = "success"
                    if isinstance(output_data, dict) and not output_data.get(
                        "success", True
                    ):
                        tool_status = "error"

                    yield _emit("tool_call_end",
                                name=tool_name, output=output_data,
                                status=tool_status,
                                duration_ms=round(duration_ms, 2),
                                tool_count=tool_count)

                    yield _emit("progress",
                                tool_name=tool_name,
                                tool_count=tool_count,
                                duration_ms=round(duration_ms, 2))

                elif kind == "on_chain_end" and self._enable_interrupt:
                    interrupt_data = event["data"].get("output")
                    if hasattr(interrupt_data, "__interrupt__"):
                        yield _emit("interrupt",
                                    detail=interrupt_data.__interrupt__[0])

        except Exception as e:
            yield _emit("error", detail=f"Graph Execution Error: {str(e)}")
