import json
import operator
from typing import AsyncGenerator, Dict, Any, List, Optional, Annotated, TypedDict, TYPE_CHECKING
from langchain_core.messages import BaseMessage, trim_messages, filter_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agents.deepseek_chat_model import DeepSeekChatOpenAI
from app.agents.registry import ToolRegistry
from app.agents.tools import ALL_TOOLS
from app.core.logging import get_logger
import time

if TYPE_CHECKING:
    from app.memory.manager import MemoryManager

logger = get_logger(__name__)
MAX_GRAPH_STEPS = 24


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
        self._db_connection = None
        self._runtime_tools = None
        self.app = None
        self._speak_prompt: Optional[str] = None
        self._enable_interrupt = enable_interrupt

    def _get_tools(self):
        return self._runtime_tools or self.registry.get_all()

    async def _ensure_checkpointer(self):
        if self.checkpointer is None:
            import aiosqlite
            conn = await aiosqlite.connect(self._db_path)
            self._db_connection = conn
            self.checkpointer = AsyncSqliteSaver(conn)
            # Resolve local and MCP tools once per workflow instance so the
            # graph, model binding and ToolNode share the same tool set.
            self._runtime_tools = await self.registry.get_runtime_tools()
            self.app = self._compile_graph()

    async def close(self) -> None:
        """Release resources owned by this workflow instance."""
        connection = self._db_connection
        self._db_connection = None
        self.checkpointer = None
        self.app = None
        self._runtime_tools = None
        if connection is not None:
            await connection.close()

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
        additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
        reasoning_content = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning_content, str):
            reasoning_trace = reasoning_content
        elif isinstance(self.llm, DeepSeekChatOpenAI):
            # DeepSeek's visible `content` is an answer/tool draft, not hidden
            # reasoning. Never persist that draft as the reasoning trace.
            reasoning_trace = ""
        else:
            reasoning_trace = response.content if hasattr(response, "content") else ""
        return {
            "messages": [response],
            "reasoning_trace": reasoning_trace,
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
        deepseek_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        await self._ensure_checkpointer()
        self._speak_prompt = speak_prompt
        llm_kwargs: Dict[str, Any] = {
            "model": model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "streaming": True,
            # Do not leave a browser request pending forever when the upstream
            # provider accepts a connection but never starts streaming.
            "timeout": 90,
        }
        is_deepseek = deepseek_options is not None or "api.deepseek.com" in self.base_url.lower()
        thinking_enabled = bool(deepseek_options and deepseek_options.get("thinking", True))
        if is_deepseek and deepseek_options:
            effort = deepseek_options.get("reasoning_effort", "high")
            llm_kwargs["extra_body"] = {
                "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
            }
            if thinking_enabled:
                llm_kwargs["reasoning_effort"] = effort if effort in {"high", "max"} else "high"
            else:
                llm_kwargs["temperature"] = temperature
        else:
            llm_kwargs["temperature"] = temperature

        llm_class = DeepSeekChatOpenAI if is_deepseek else ChatOpenAI
        self.llm = llm_class(**llm_kwargs)
        self.llm_with_tools = self.llm.bind_tools(self._get_tools())

        enriched_messages = list(messages)
        if self.memory and thread_id:
            user_query = next((m["content"] for m in reversed(messages)
                              if m.get("role") == "user"), "")
            if user_query:
                ctx = await self.memory.retrieve_context(thread_id, user_query)
                if ctx.summary:
                    enriched_messages.insert(0, {"role": "system", "content": ctx.summary})

        # Bound think/tool cycles so a malformed tool response or provider
        # loop cannot consume an unbounded request budget.
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": MAX_GRAPH_STEPS,
        }

        tool_count: int = 0
        tool_start_times: Dict[str, float] = {}
        active_tool_calls_by_index: Dict[int, Dict[str, Any]] = {}
        pending_tool_calls: List[Dict[str, Any]] = []
        tool_runtime_call_ids: Dict[str, str] = {}
        deferred_tool_starts: Dict[str, Dict[str, Any]] = {}
        # The API layer emits an immediate placeholder thinking_start before
        # this workflow begins. Treat that placeholder as active so the first
        # tool call or answer chunk closes it instead of leaving the UI spinner
        # pending forever when the provider emits no visible reasoning tokens.
        _thinking_active: bool = True
        _message_started: bool = False
        _last_reasoning: str = ""

        def _emit(event_type: str, **kwargs) -> Dict[str, Any]:
            return {"type": event_type, **kwargs}

        def _parse_tool_args(raw_args: str):
            try:
                return json.loads(raw_args) if raw_args else {}
            except (TypeError, json.JSONDecodeError):
                return None

        def _match_pending_tool_call(tool_name: str, inputs: Any):
            candidates = [call for call in pending_tool_calls if call.get("name") == tool_name]
            exact = [
                call for call in candidates
                if _parse_tool_args(call.get("args", "")) == inputs
            ]
            matched = exact[0] if len(exact) == 1 else (
                candidates[0] if len(candidates) == 1 else None
            )
            if matched is not None:
                pending_tool_calls.remove(matched)
            return matched, bool(candidates)

        # Keep the workflow usable outside the HTTP endpoint too. The API layer
        # sends the same placeholder earlier to flush the response immediately;
        # the frontend coalesces the duplicate start event.
        yield _emit("thinking_start")

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
                            index = tc.get("index", 0)
                            call = active_tool_calls_by_index.setdefault(index, {
                                "id": None,
                                "name": None,
                                "args": "",
                            })
                            if tc.get("id"):
                                call["id"] = tc["id"]
                            if tc.get("name"):
                                call["name"] = tc["name"]
                            call["args"] += tc.get("args", "")
                            if call["id"] and call["name"]:
                                yield _emit("tool_call_delta",
                                            id=call["id"], name=call["name"],
                                            delta=tc.get("args", ""))

                    reasoning_delta = getattr(chunk, "reasoning_content", None)
                    if not reasoning_delta:
                        reasoning_delta = getattr(chunk, "additional_kwargs", {}).get(
                            "reasoning_content"
                        )
                    if reasoning_delta and node_name in ("think", "speak"):
                        if not _thinking_active:
                            _thinking_active = True
                            _last_reasoning = ""
                            yield _emit("thinking_start")
                        _last_reasoning += reasoning_delta
                        yield _emit("thinking_chunk", content=reasoning_delta)

                    if node_name == "think" and not is_deepseek:
                        # Providers without a separate reasoning field expose
                        # the internal think-node text as content. DeepSeek is
                        # handled above via reasoning_content and must not send
                        # its visible answer draft into the thinking stream.
                        delta = (
                            chunk.content if hasattr(chunk, "content") and isinstance(chunk.content, str) else ""
                        )
                        if not delta:
                            continue
                        if not _thinking_active:
                            _thinking_active = True
                            _last_reasoning = ""
                            yield _emit("thinking_start")
                        _last_reasoning += delta
                        yield _emit("thinking_chunk", content=delta)

                    elif node_name == "speak":
                        if not (hasattr(chunk, "content") and isinstance(chunk.content, str)
                                and chunk.content):
                            continue
                        delta = chunk.content
                        if _thinking_active:
                            _thinking_active = False
                            yield _emit("thinking_end")
                        if not _message_started:
                            _message_started = True
                            yield _emit("message_start")
                        yield _emit("message_chunk", content=delta)

                elif kind == "on_chat_model_end":
                    if node_name == "think":
                        if active_tool_calls_by_index:
                            pending_tool_calls.extend(active_tool_calls_by_index.values())
                            active_tool_calls_by_index.clear()
                        if _thinking_active:
                            yield _emit("thinking_end")
                            _thinking_active = False
                        if _last_reasoning:
                            yield _emit("reasoning_trace", content=_last_reasoning)
                    elif node_name == "speak":
                        if _thinking_active:
                            yield _emit("thinking_end")
                            _thinking_active = False
                        if _message_started:
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
                    matched_call, had_candidates = _match_pending_tool_call(tool_name, inputs)
                    tool_call_id = matched_call.get("id") if matched_call else None
                    tool_runtime_call_ids[run_id] = tool_call_id or ""
                    tool_start_times[run_id] = time.perf_counter()
                    if tool_call_id:
                        yield _emit("tool_call_start", id=tool_call_id, name=tool_name, inputs=inputs)
                    elif had_candidates:
                        # Identical concurrent calls cannot be distinguished from
                        # on_tool_start alone. Wait for ToolMessage.tool_call_id.
                        deferred_tool_starts[run_id] = {
                            "name": tool_name,
                            "inputs": inputs,
                        }
                    else:
                        yield _emit("tool_call_start", id=run_id, name=tool_name, inputs=inputs)

                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    run_id = event["run_id"]
                    duration_ms = 0.0
                    if run_id in tool_start_times:
                        duration_ms = (
                            time.perf_counter() - tool_start_times.pop(run_id)
                        ) * 1000

                    raw_output = event["data"].get("output")
                    runtime_tool_call_id = tool_runtime_call_ids.pop(run_id, "")
                    output_tool_call_id = getattr(raw_output, "tool_call_id", None)
                    tool_call_id = (
                        output_tool_call_id
                        or runtime_tool_call_id
                        or run_id
                    )
                    deferred_start = deferred_tool_starts.pop(run_id, None)
                    if deferred_start:
                        if output_tool_call_id:
                            matched_pending = next(
                                (
                                    call for call in pending_tool_calls
                                    if call.get("id") == output_tool_call_id
                                ),
                                None,
                            )
                            if matched_pending is not None:
                                pending_tool_calls.remove(matched_pending)
                        yield _emit(
                            "tool_call_start",
                            id=tool_call_id,
                            name=deferred_start["name"],
                            inputs=deferred_start["inputs"],
                        )
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
                                id=tool_call_id, name=tool_name, output=output_data,
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
