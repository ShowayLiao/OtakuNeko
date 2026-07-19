import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agents.graph import (
    ChatWorkflow,
    CodingAgentState,
    THINK_SYSTEM_PROMPT,
    SPEAK_SYSTEM_PROMPT,
)


def _msg_role(msg):
    if isinstance(msg, dict):
        return msg.get("role")
    return getattr(msg, "role", None)


def _msg_content(msg):
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", "")


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def state_without_tool_calls():
    return {
        "messages": [
            HumanMessage(content="推荐一部动画"),
            AIMessage(content="我来搜索一下"),
        ],
        "reasoning_trace": "",
        "current_dir": "",
        "plan": "",
        "completed_steps": [],
        "last_terminal_output": "",
    }


@pytest.fixture
def state_with_tool_calls():
    return {
        "messages": [
            HumanMessage(content="推荐一部动画"),
            AIMessage(
                content="",
                tool_calls=[{"name": "search_anime", "args": {"keyword": "科幻"}, "id": "call_1"}],
            ),
        ],
        "reasoning_trace": "",
        "current_dir": "",
        "plan": "",
        "completed_steps": [],
        "last_terminal_output": "",
    }


@pytest.fixture
def state_with_empty_tool_calls():
    return {
        "messages": [
            HumanMessage(content="hello"),
            AIMessage(content="hi", tool_calls=[]),
        ],
        "reasoning_trace": "",
        "current_dir": "",
        "plan": "",
        "completed_steps": [],
        "last_terminal_output": "",
    }


@pytest.fixture
def workflow():
    return ChatWorkflow(api_key="sk-test", base_url="https://test.api")


# ============================================================================
# CodingAgentState — 六字段结构
# ============================================================================

class TestCodingAgentState:
    def test_state_contains_six_fields(self):
        fields = list(CodingAgentState.__annotations__.keys())
        assert "messages" in fields
        assert "reasoning_trace" in fields
        assert "current_dir" in fields
        assert "plan" in fields
        assert "completed_steps" in fields
        assert "last_terminal_output" in fields
        assert len(fields) == 6

    def test_reasoning_trace_defaults_to_empty_string(self):
        state: CodingAgentState = {
            "messages": [],
            "reasoning_trace": "",
            "current_dir": "",
            "plan": "",
            "completed_steps": [],
            "last_terminal_output": "",
        }
        assert state["reasoning_trace"] == ""


# ============================================================================
# System Prompts — 常量完整性
# ============================================================================

class TestSystemPrompts:
    def test_think_prompt_is_non_empty_and_contains_keywords(self):
        assert len(THINK_SYSTEM_PROMPT) > 0
        assert "推理" in THINK_SYSTEM_PROMPT
        assert "工具" in THINK_SYSTEM_PROMPT
        assert "不需要给出最终回复" in THINK_SYSTEM_PROMPT

    def test_speak_prompt_is_non_empty_and_contains_keywords(self):
        assert len(SPEAK_SYSTEM_PROMPT) > 0
        assert "助手" in SPEAK_SYSTEM_PROMPT or "二次元" in SPEAK_SYSTEM_PROMPT
        assert "不要" in SPEAK_SYSTEM_PROMPT and "工具" in SPEAK_SYSTEM_PROMPT


# ============================================================================
# _think_condition — 路由逻辑
# ============================================================================

class TestThinkCondition:
    def test_returns_speak_when_last_message_has_no_tool_calls(
        self, workflow, state_without_tool_calls
    ):
        result = workflow._think_condition(state_without_tool_calls)
        assert result == "speak"

    def test_returns_tools_when_last_message_has_tool_calls(
        self, workflow, state_with_tool_calls
    ):
        result = workflow._think_condition(state_with_tool_calls)
        assert result == "tools"

    def test_returns_speak_when_tool_calls_is_empty_list(
        self, workflow, state_with_empty_tool_calls
    ):
        result = workflow._think_condition(state_with_empty_tool_calls)
        assert result == "speak"

    def test_returns_speak_when_last_message_is_human(self, workflow):
        state = {
            "messages": [HumanMessage(content="hello")],
            "reasoning_trace": "",
            "current_dir": "",
            "plan": "",
            "completed_steps": [],
            "last_terminal_output": "",
        }
        result = workflow._think_condition(state)
        assert result == "speak"


# ============================================================================
# _strip_orphaned_tool_calls — 孤儿 tool_call 清理
# ============================================================================

class TestStripOrphanedToolCalls:
    def test_removes_ai_message_with_orphaned_tool_calls(self):
        messages = [
            HumanMessage(content="call a tool"),
            AIMessage(
                content="",
                tool_calls=[{"name": "search", "args": {}, "id": "orphan_1"}],
            ),
        ]
        cleaned = ChatWorkflow._strip_orphaned_tool_calls(messages)
        assert len(cleaned) == 1
        assert isinstance(cleaned[0], HumanMessage)

    def test_keeps_ai_message_when_tool_result_exists(self):
        messages = [
            HumanMessage(content="call a tool"),
            AIMessage(
                content="",
                tool_calls=[{"name": "search", "args": {}, "id": "call_1"}],
            ),
            ToolMessage(content="result", tool_call_id="call_1"),
        ]
        cleaned = ChatWorkflow._strip_orphaned_tool_calls(messages)
        assert len(cleaned) == 3

    def test_drops_entire_ai_message_when_any_tool_call_is_orphaned(self):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "valid", "args": {}, "id": "ok"},
                    {"name": "orphan", "args": {}, "id": "gone"},
                ],
            ),
            ToolMessage(content="ok_result", tool_call_id="ok"),
        ]
        cleaned = ChatWorkflow._strip_orphaned_tool_calls(messages)
        assert len(cleaned) == 2
        assert isinstance(cleaned[0], HumanMessage)

    def test_preserves_messages_without_tool_calls(self):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
            HumanMessage(content="thanks"),
        ]
        cleaned = ChatWorkflow._strip_orphaned_tool_calls(messages)
        assert len(cleaned) == 3


# ============================================================================
# _compile_graph — 图拓扑
# ============================================================================

class TestCompileGraph:
    def test_graph_has_think_speak_tools_nodes(self, workflow, temp_db_path):
        import asyncio

        async def _run():
            workflow._db_path = temp_db_path
            await workflow._ensure_checkpointer()
            nodes = list(workflow.app.get_graph().nodes.keys())
            assert "think" in nodes
            assert "speak" in nodes
            assert "tools" in nodes

        asyncio.run(_run())

    def test_edge_from_tools_goes_to_think(self, workflow, temp_db_path):
        import asyncio

        async def _run():
            workflow._db_path = temp_db_path
            await workflow._ensure_checkpointer()
            edges = workflow.app.get_graph().edges
            tools_edge_found = any(
                e.source == "tools" and e.target == "think"
                for e in edges
            )
            assert tools_edge_found

        asyncio.run(_run())

    def test_enable_interrupt_adds_interrupt_before_speak(self, temp_db_path):
        import asyncio

        async def _run():
            wf = ChatWorkflow(
                api_key="sk-test", base_url="https://test.api",
                db_path=temp_db_path, enable_interrupt=True,
            )
            await wf._ensure_checkpointer()
            nodes = list(wf.app.get_graph().nodes.keys())
            assert "speak" in nodes
            assert "think" in nodes
            assert "tools" in nodes

        asyncio.run(_run())

    def test_enable_interrupt_false_does_not_set_interrupt_before(self, temp_db_path):
        import asyncio

        async def _run():
            wf = ChatWorkflow(
                api_key="sk-test", base_url="https://test.api",
                db_path=temp_db_path, enable_interrupt=False,
            )
            await wf._ensure_checkpointer()
            nodes = list(wf.app.get_graph().nodes.keys())
            assert "think" in nodes
            assert "speak" in nodes
            assert "tools" in nodes

        asyncio.run(_run())


# ============================================================================
# _think_node — 直接方法调用（mock LLM）
# ============================================================================

class TestThinkNode:
    @pytest.mark.asyncio
    async def test_returns_messages_and_reasoning_trace(self, workflow, state_without_tool_calls):
        fake_response = AIMessage(
            content="准备给用户的可见草稿",
            additional_kwargs={"reasoning_content": "分析: 用户想要搜索科幻动画"},
        )
        workflow.llm_with_tools = MagicMock()
        workflow.llm_with_tools.ainvoke = AsyncMock(return_value=fake_response)
        workflow.llm = MagicMock()

        result = await workflow._think_node(state_without_tool_calls)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0] is fake_response
        assert result["reasoning_trace"] == "分析: 用户想要搜索科幻动画"

    @pytest.mark.asyncio
    async def test_reasoning_trace_is_empty_when_no_content(self, workflow, state_without_tool_calls):
        fake_response = MagicMock()
        del fake_response.content
        workflow.llm_with_tools = MagicMock()
        workflow.llm_with_tools.ainvoke = AsyncMock(return_value=fake_response)
        workflow.llm = MagicMock()

        result = await workflow._think_node(state_without_tool_calls)
        assert result["reasoning_trace"] == ""

    @pytest.mark.asyncio
    async def test_injects_think_system_prompt(self, workflow, state_without_tool_calls):
        captured_messages = []

        async def fake_ainvoke(messages):
            captured_messages.extend(messages)
            return AIMessage(content="分析完成")

        workflow.llm_with_tools = MagicMock()
        workflow.llm_with_tools.ainvoke = fake_ainvoke
        workflow.llm = MagicMock()

        await workflow._think_node(state_without_tool_calls)

        system_msgs = [m for m in captured_messages if _msg_role(m) == "system"]
        assert len(system_msgs) == 1
        assert "推理" in _msg_content(system_msgs[0])


# ============================================================================
# _speak_node — 直接方法调用（mock LLM）
# ============================================================================

class TestSpeakNode:
    @pytest.mark.asyncio
    async def test_returns_messages_only_no_reasoning_trace(self, workflow, state_without_tool_calls):
        fake_response = AIMessage(content="根据分析，推荐《星际牛仔》")
        workflow.llm = MagicMock()
        workflow.llm.ainvoke = AsyncMock(return_value=fake_response)
        workflow._speak_prompt = None
        workflow.llm_with_tools = MagicMock()

        result = await workflow._speak_node(state_without_tool_calls)

        assert "messages" in result
        assert result["messages"][0] is fake_response
        assert "reasoning_trace" not in result

    @pytest.mark.asyncio
    async def test_uses_llm_not_llm_with_tools(self, workflow, state_without_tool_calls):
        workflow.llm = MagicMock()
        workflow.llm.ainvoke = AsyncMock(return_value=AIMessage(content="回复"))
        workflow.llm_with_tools = MagicMock()
        workflow.llm_with_tools.ainvoke = AsyncMock()
        workflow._speak_prompt = None

        await workflow._speak_node(state_without_tool_calls)

        workflow.llm.ainvoke.assert_called_once()
        workflow.llm_with_tools.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_custom_speak_prompt_when_set(self, workflow, state_without_tool_calls):
        captured_messages = []

        async def fake_ainvoke(messages):
            captured_messages.extend(messages)
            return AIMessage(content="回复")

        workflow.llm = MagicMock()
        workflow.llm.ainvoke = fake_ainvoke
        workflow.llm_with_tools = MagicMock()
        workflow._speak_prompt = "[角色设定]\n你是一只猫娘"

        await workflow._speak_node(state_without_tool_calls)

        system_msgs = [m for m in captured_messages if _msg_role(m) == "system"]
        assert any("猫娘" in _msg_content(m) for m in system_msgs)

    @pytest.mark.asyncio
    async def test_falls_back_to_default_speak_prompt_when_none(self, workflow, state_without_tool_calls):
        captured_messages = []

        async def fake_ainvoke(messages):
            captured_messages.extend(messages)
            return AIMessage(content="回复")

        workflow.llm = MagicMock()
        workflow.llm.ainvoke = fake_ainvoke
        workflow.llm_with_tools = MagicMock()
        workflow._speak_prompt = None

        await workflow._speak_node(state_without_tool_calls)

        system_msgs = [m for m in captured_messages if _msg_role(m) == "system"]
        assert len(system_msgs) == 1
        content = _msg_content(system_msgs[0])
        assert "助手" in content or "二次元" in content


# ============================================================================
# stream_chat 事件流 — mock astream_events 验证 SSE 翻译逻辑
# ============================================================================

def _stream_event(kind, node_name, content=None, tool_chunks=None,
                  tool_name=None, tool_inputs=None, tool_output=None,
                  tool_run_id="run-1", chain_output=None):
    return {
        "event": kind,
        "data": {
            "chunk": _make_chunk(content, tool_chunks),
            "input": tool_inputs or {},
            "output": tool_output if kind == "on_tool_end" else chain_output,
        },
        "metadata": {"langgraph_node": node_name},
        "name": tool_name or "",
        "run_id": tool_run_id,
    }


class _FakeChunk:
    def __init__(self, content="", tool_call_chunks=None):
        self.content = content
        self.tool_call_chunks = tool_call_chunks


def _make_chunk(content, tool_chunks):
    return _FakeChunk(content=content, tool_call_chunks=tool_chunks)


def _make_tool_chunk(name, args_delta, tc_id="tc-1"):
    return [{"name": name, "args": args_delta, "id": tc_id}]


class TestStreamChatEventFlow:
    @pytest.mark.asyncio
    async def test_think_node_produces_thinking_start_chunk_end_events(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        fake_events = [
            _stream_event("on_chat_model_stream", "think", content="推理过程..."),
            _stream_event("on_chat_model_end", "think"),
            _stream_event("on_chat_model_stream", "speak", content="最终回复"),
            _stream_event("on_chat_model_end", "speak"),
        ]

        async def fake_astream(*args, **kwargs):
            for e in fake_events:
                yield e

        wf.app.astream_events = fake_astream

        events = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "推荐动画"}],
            temperature=0.6,
            thread_id="test-think-events",
        ):
            events.append(event)

        thinking_starts = [e for e in events if e["type"] == "thinking_start"]
        thinking_chunks = [e for e in events if e["type"] == "thinking_chunk"]
        thinking_ends = [e for e in events if e["type"] == "thinking_end"]
        reasoning_traces = [e for e in events if e["type"] == "reasoning_trace"]
        message_starts = [e for e in events if e["type"] == "message_start"]
        message_chunks = [e for e in events if e["type"] == "message_chunk"]
        message_ends = [e for e in events if e["type"] == "message_end"]

        assert len(thinking_starts) == 1
        assert len(thinking_chunks) == 1
        assert thinking_chunks[0]["content"] == "推理过程..."
        assert len(thinking_ends) >= 1
        assert len(reasoning_traces) == 1
        assert reasoning_traces[0]["content"] == "推理过程..."
        assert len(message_starts) == 1
        assert len(message_chunks) == 1
        assert message_chunks[0]["content"] == "最终回复"
        assert len(message_ends) == 1

    @pytest.mark.asyncio
    async def test_reasoning_trace_not_emitted_when_empty(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        fake_events = [
            _stream_event("on_chat_model_end", "think"),
            _stream_event("on_chat_model_stream", "speak", content="回复"),
            _stream_event("on_chat_model_end", "speak"),
        ]

        async def fake_astream(*args, **kwargs):
            for e in fake_events:
                yield e

        wf.app.astream_events = fake_astream

        events = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.6,
            thread_id="test-empty-reasoning",
        ):
            events.append(event)

        reasoning_traces = [e for e in events if e["type"] == "reasoning_trace"]
        assert len(reasoning_traces) == 0

    @pytest.mark.asyncio
    async def test_speak_node_produces_message_start_chunk_end(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        fake_events = [
            _stream_event("on_chat_model_stream", "think", content="推理"),
            _stream_event("on_chat_model_end", "think"),
            _stream_event("on_chat_model_stream", "speak", content="最终回复内容"),
            _stream_event("on_chat_model_end", "speak"),
        ]

        async def fake_astream(*args, **kwargs):
            for e in fake_events:
                yield e

        wf.app.astream_events = fake_astream

        events = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.6,
            thread_id="test-speak-events",
        ):
            events.append(event)

        message_starts = [e for e in events if e["type"] == "message_start"]
        message_chunks = [e for e in events if e["type"] == "message_chunk"]
        message_ends = [e for e in events if e["type"] == "message_end"]

        assert len(message_starts) == 1
        assert len(message_chunks) == 1
        assert message_chunks[0]["content"] == "最终回复内容"
        assert len(message_ends) == 1

    @pytest.mark.asyncio
    async def test_event_order_is_thinking_then_reasoning_then_message(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        fake_events = [
            _stream_event("on_chat_model_stream", "think", content="推理"),
            _stream_event("on_chat_model_end", "think"),
            _stream_event("on_chat_model_stream", "speak", content="回复"),
            _stream_event("on_chat_model_end", "speak"),
        ]

        async def fake_astream(*args, **kwargs):
            for e in fake_events:
                yield e

        wf.app.astream_events = fake_astream

        event_types = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.6,
            thread_id="test-order",
        ):
            event_types.append(event["type"])

        assert event_types == [
            "thinking_start", "thinking_chunk",
            "thinking_end", "reasoning_trace",
            "message_start", "message_chunk",
            "message_end",
        ]

    @pytest.mark.asyncio
    async def test_speak_prompt_is_passed_to_speak_node(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        fake_events = [
            _stream_event("on_chat_model_stream", "think", content="推理"),
            _stream_event("on_chat_model_end", "think"),
            _stream_event("on_chat_model_stream", "speak", content="回复"),
            _stream_event("on_chat_model_end", "speak"),
        ]

        async def fake_astream(*args, **kwargs):
            for e in fake_events:
                yield e

        wf.app.astream_events = fake_astream

        events = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.6,
            thread_id="test-speak-prompt",
            speak_prompt="[角色设定]\n你是哆啦A梦",
        ):
            events.append(event)

        assert wf._speak_prompt is not None
        assert "哆啦A梦" in wf._speak_prompt

    @pytest.mark.asyncio
    async def test_error_event_on_exception(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        async def fake_astream_raise(*args, **kwargs):
            raise RuntimeError("LLM 不可用")
            yield

        wf.app.astream_events = fake_astream_raise

        events = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.6,
            thread_id="test-error",
        ):
            events.append(event)

        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert "LLM 不可用" in errors[0]["detail"]

    @pytest.mark.asyncio
    async def test_tool_call_delta_events_are_emitted(self, temp_db_path):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", db_path=temp_db_path)
        await wf._ensure_checkpointer()

        fake_events = [
            _stream_event(
                "on_chat_model_stream", "think",
                tool_chunks=_make_tool_chunk("search_anime", '{"keyword":'),
            ),
            _stream_event(
                "on_chat_model_stream", "think",
                tool_chunks=_make_tool_chunk("search_anime", ' "科幻"}', tc_id="tc-1"),
            ),
            _stream_event("on_chat_model_end", "think"),
            _stream_event("on_chat_model_stream", "speak", content="回复"),
            _stream_event("on_chat_model_end", "speak"),
        ]

        async def fake_astream(*args, **kwargs):
            for e in fake_events:
                yield e

        wf.app.astream_events = fake_astream

        events = []
        async for event in wf.stream_chat(
            model="test-model",
            messages=[{"role": "user", "content": "搜索科幻动画"}],
            temperature=0.6,
            thread_id="test-tool-delta",
        ):
            events.append(event)

        deltas = [e for e in events if e["type"] == "tool_call_delta"]
        assert len(deltas) == 2
        assert deltas[0]["name"] == "search_anime"
        assert deltas[0]["delta"] == '{"keyword":'


# ============================================================================
# enable_interrupt — 中断模式
# ============================================================================

class TestEnableInterrupt:
    def test_default_is_false(self, workflow):
        assert workflow._enable_interrupt is False

    def test_true_when_passed(self):
        wf = ChatWorkflow(api_key="sk-test", base_url="https://test.api", enable_interrupt=True)
        assert wf._enable_interrupt is True


# ============================================================================
# _trim_and_clean — 消息清洗
# ============================================================================

class TestTrimAndClean:
    def test_keeps_standard_message_types(self, workflow):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
            SystemMessage(content="system"),
            ToolMessage(content="result", tool_call_id="id1"),
        ]
        workflow.llm = MagicMock()
        cleaned = workflow._trim_and_clean(messages)
        assert len(cleaned) == 4

    def test_removes_orphaned_tool_calls_during_clean(self, workflow):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="", tool_calls=[{"name": "orphan", "args": {}, "id": "gone"}]),
        ]
        workflow.llm = MagicMock()
        cleaned = workflow._trim_and_clean(messages)
        assert len(cleaned) == 1
        assert isinstance(cleaned[0], HumanMessage)


# ============================================================================
# CodingAgentState — checkpoint 序列化兼容
# ============================================================================

class TestStateCheckpointRoundtrip:
    @pytest.mark.asyncio
    async def test_reasoning_trace_persists_in_checkpoint(self, temp_db_path):
        from langgraph.graph import StateGraph, START, END

        def write_trace(state: CodingAgentState):
            return {"reasoning_trace": "分析完成", "messages": [AIMessage(content="done")]}

        workflow = StateGraph(CodingAgentState)
        workflow.add_node("w", write_trace)
        workflow.add_edge(START, "w")
        workflow.add_edge("w", END)

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver:
            app = workflow.compile(checkpointer=saver)
            config = {"configurable": {"thread_id": "trace-1", "checkpoint_ns": ""}}
            result = await app.ainvoke(
                {
                    "messages": [HumanMessage(content="hi")],
                    "reasoning_trace": "",
                    "current_dir": "",
                    "plan": "",
                    "completed_steps": [],
                    "last_terminal_output": "",
                },
                config,
            )
            assert result["reasoning_trace"] == "分析完成"

            cp = await saver.aget_tuple(config)
            channel_values = cp.checkpoint["channel_values"]
            assert channel_values.get("reasoning_trace") == "分析完成"
