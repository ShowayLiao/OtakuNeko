import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages.ai import AIMessageChunk

from app.agents.deepseek_chat_model import DeepSeekChatOpenAI
from app.agents.graph import ChatWorkflow


def make_model() -> DeepSeekChatOpenAI:
    return DeepSeekChatOpenAI(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )


def test_preserves_reasoning_content_from_stream_delta():
    model = make_model()

    generation = model._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "正在分析用户请求",
                    },
                    "finish_reason": None,
                    "logprobs": None,
                }
            ]
        },
        AIMessageChunk,
        None,
    )

    assert generation is not None
    assert generation.message.additional_kwargs["reasoning_content"] == "正在分析用户请求"


def test_returns_reasoning_content_with_tool_call_followup():
    model = make_model()
    messages = [
        HumanMessage(content="查一下动画"),
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "需要调用搜索工具"},
            tool_calls=[{
                "name": "search_anime_advanced",
                "args": {"keyword": "动画"},
                "id": "call-1",
                "type": "tool_call",
            }],
        ),
        ToolMessage(content="[]", tool_call_id="call-1"),
    ]

    payload = model._get_request_payload(messages)

    assert payload["messages"][1]["reasoning_content"] == "需要调用搜索工具"


@pytest.mark.asyncio
async def test_graph_forwards_reasoning_from_think_and_speak_nodes():
    workflow = ChatWorkflow(api_key="test-key", base_url="https://deepseek-proxy.example/v1")

    async def ensure_fake_app():
        return None

    class FakeApp:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "think"},
                "data": {"chunk": AIMessageChunk(
                    content="判断完成",
                    additional_kwargs={"reasoning_content": "先判断是否需要工具"},
                    tool_call_chunks=[{
                        "name": "search_anime_advanced",
                        "args": '{"keyword":"动画"}',
                        "id": "call-combined",
                        "index": 0,
                        "type": "tool_call_chunk",
                    }],
                )},
            }
            yield {
                "event": "on_chat_model_end",
                "metadata": {"langgraph_node": "think"},
                "data": {},
            }
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "speak"},
                "data": {"chunk": AIMessageChunk(
                    content="",
                    additional_kwargs={"reasoning_content": "组织最终回答"},
                )},
            }
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "speak"},
                "data": {"chunk": AIMessageChunk(content="最终回答")},
            }
            yield {
                "event": "on_chat_model_end",
                "metadata": {"langgraph_node": "speak"},
                "data": {},
            }

    workflow._ensure_checkpointer = ensure_fake_app  # type: ignore[method-assign]
    workflow.app = FakeApp()

    events = [event async for event in workflow.stream_chat(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "你好"}],
        temperature=0.6,
        deepseek_options={"thinking": True, "reasoning_effort": "high"},
    )]

    assert isinstance(workflow.llm, DeepSeekChatOpenAI)
    assert [(event["type"], event.get("content")) for event in events] == [
        ("thinking_start", None),
        ("tool_call_delta", None),
        ("thinking_chunk", "先判断是否需要工具"),
        ("thinking_end", None),
        ("reasoning_trace", "先判断是否需要工具"),
        ("thinking_start", None),
        ("thinking_chunk", "组织最终回答"),
        ("thinking_end", None),
        ("message_start", None),
        ("message_chunk", "最终回答"),
        ("message_end", None),
    ]


@pytest.mark.asyncio
async def test_same_name_tools_bind_ids_by_arguments_when_start_order_changes():
    workflow = ChatWorkflow(api_key="test-key", base_url="https://api.deepseek.com")

    async def ensure_fake_app():
        return None

    class FakeApp:
        async def astream_events(self, *_args, **_kwargs):
            for call_id, keyword, index in (("call-a", "A", 0), ("call-b", "B", 1)):
                yield {
                    "event": "on_chat_model_stream",
                    "metadata": {"langgraph_node": "think"},
                    "data": {"chunk": AIMessageChunk(
                        content="",
                        tool_call_chunks=[{
                            "name": "search_anime_advanced",
                            "args": f'{{"keyword":"{keyword}"}}',
                            "id": call_id,
                            "index": index,
                            "type": "tool_call_chunk",
                        }],
                    )},
                }
            yield {
                "event": "on_chat_model_end",
                "metadata": {"langgraph_node": "think"},
                "data": {},
            }
            for run_id, keyword in (("run-b", "B"), ("run-a", "A")):
                yield {
                    "event": "on_tool_start",
                    "name": "search_anime_advanced",
                    "run_id": run_id,
                    "data": {"input": {"keyword": keyword}},
                }
            for run_id, call_id in (("run-b", "call-b"), ("run-a", "call-a")):
                yield {
                    "event": "on_tool_end",
                    "name": "search_anime_advanced",
                    "run_id": run_id,
                    "data": {"output": ToolMessage(content="[]", tool_call_id=call_id)},
                }

    workflow._ensure_checkpointer = ensure_fake_app  # type: ignore[method-assign]
    workflow.app = FakeApp()

    events = [event async for event in workflow.stream_chat(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "搜索"}],
        temperature=0.6,
        deepseek_options={"thinking": True, "reasoning_effort": "high"},
    )]

    runtime_events = [
        (event["type"], event["id"])
        for event in events
        if event["type"] in ("tool_call_start", "tool_call_end")
    ]
    assert runtime_events == [
        ("tool_call_start", "call-b"),
        ("tool_call_start", "call-a"),
        ("tool_call_end", "call-b"),
        ("tool_call_end", "call-a"),
    ]


@pytest.mark.asyncio
async def test_identical_concurrent_tools_defer_start_until_real_id_is_known():
    workflow = ChatWorkflow(api_key="test-key", base_url="https://api.deepseek.com")

    async def ensure_fake_app():
        return None

    class FakeApp:
        async def astream_events(self, *_args, **_kwargs):
            for call_id, index in (("call-a", 0), ("call-b", 1)):
                yield {
                    "event": "on_chat_model_stream",
                    "metadata": {"langgraph_node": "think"},
                    "data": {"chunk": AIMessageChunk(
                        content="",
                        tool_call_chunks=[{
                            "name": "search_anime_advanced",
                            "args": '{"keyword":"same"}',
                            "id": call_id,
                            "index": index,
                            "type": "tool_call_chunk",
                        }],
                    )},
                }
            yield {
                "event": "on_chat_model_end",
                "metadata": {"langgraph_node": "think"},
                "data": {},
            }
            for run_id in ("run-b", "run-a"):
                yield {
                    "event": "on_tool_start",
                    "name": "search_anime_advanced",
                    "run_id": run_id,
                    "data": {"input": {"keyword": "same"}},
                }
            for run_id, call_id in (("run-b", "call-b"), ("run-a", "call-a")):
                yield {
                    "event": "on_tool_end",
                    "name": "search_anime_advanced",
                    "run_id": run_id,
                    "data": {"output": ToolMessage(content="[]", tool_call_id=call_id)},
                }

    workflow._ensure_checkpointer = ensure_fake_app  # type: ignore[method-assign]
    workflow.app = FakeApp()

    events = [event async for event in workflow.stream_chat(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "search"}],
        temperature=0.6,
        deepseek_options={"thinking": True, "reasoning_effort": "high"},
    )]

    runtime_events = [
        (event["type"], event["id"])
        for event in events
        if event["type"] in ("tool_call_start", "tool_call_end")
    ]
    assert runtime_events == [
        ("tool_call_start", "call-b"),
        ("tool_call_end", "call-b"),
        ("tool_call_start", "call-a"),
        ("tool_call_end", "call-a"),
    ]


@pytest.mark.asyncio
async def test_placeholder_thinking_closes_before_tool_start_without_reasoning_tokens():
    workflow = ChatWorkflow(api_key="test-key", base_url="https://api.deepseek.com")

    async def ensure_fake_app():
        return None

    class FakeApp:
        async def astream_events(self, *_args, **_kwargs):
            yield {
                "event": "on_tool_start",
                "name": "search_anime_advanced",
                "run_id": "run-1",
                "data": {"input": {"keyword": "same"}},
            }

    workflow._ensure_checkpointer = ensure_fake_app  # type: ignore[method-assign]
    workflow.app = FakeApp()

    events = [event async for event in workflow.stream_chat(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "search"}],
        temperature=0.6,
        deepseek_options={"thinking": True, "reasoning_effort": "high"},
    )]

    assert [event["type"] for event in events] == [
        "thinking_start",
        "thinking_end",
        "tool_call_start",
    ]
