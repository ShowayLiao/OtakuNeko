import os
import json
import time
from collections import OrderedDict
from uuid import uuid4
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
from openai import AsyncOpenAI
from langgraph.store.memory import InMemoryStore
from app.schemas.agent import ChatRequest
from app.schemas.user import UserRead
from app.agents.graph import ChatWorkflow
from app.agents.langgraph_adapter import LangGraphAdapter
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.memory.manager import MemoryManager  # kept for backward compat
from app.memory.service import MemoryServiceImpl
from app.memory.repository import StoreMemoryRepository
from app.memory.extractor import LLMFactExtractor
from app.api.deps import get_current_user, get_optional_user
from app.agents.thread_scope import (
    make_anonymous_thread,
    make_user_thread,
    public_thread_id,
    user_thread_prefix,
)
from app.agents.provider_endpoint import (
    is_local_endpoint,
    validate_provider_endpoint,
)
from app.core.config import settings

from app.trace.store import InMemoryTraceStore
import app.api.v1.trace as trace_module

router = APIRouter()

_store = InMemoryStore()
_trace_store = InMemoryTraceStore(max_traces=500)
trace_module.init_trace_store(_trace_store)
_memory_services: OrderedDict[tuple[str, str], MemoryServiceImpl] = OrderedDict()
_MAX_MEMORY_MANAGERS = 32


def _get_or_create_memory(api_key: str, base_url: str) -> MemoryServiceImpl:
    key = (api_key, base_url)
    service = _memory_services.pop(key, None)
    if service is None:
        repository = StoreMemoryRepository(_store)
        extractor = LLMFactExtractor(api_key=api_key, base_url=base_url)
        service = MemoryServiceImpl(
            repository=repository,
            extractor=extractor,
            api_key=api_key,
            base_url=base_url,
        )
    _memory_services[key] = service
    while len(_memory_services) > _MAX_MEMORY_MANAGERS:
        _memory_services.popitem(last=False)
    return service


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_chat_thread(user: Optional[UserRead], requested_id: Optional[str]):
    """Resolve a public thread id to an owner-scoped checkpointer key."""
    if user is None:
        # Anonymous conversations are intentionally ephemeral.  A caller must
        # not be able to select a shared or previously persisted thread.
        return make_anonymous_thread()

    public_id = requested_id or uuid4().hex
    try:
        return make_user_thread(user.id, public_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _resolve_user_thread(user: UserRead, requested_id: str):
    try:
        return make_user_thread(user.id, requested_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _resolve_provider_base_url(value: Optional[str]) -> str:
    try:
        base_url = validate_provider_endpoint(
            value or "https://api.openai.com/v1",
            allow_local=settings.DEPLOY_MODE == "local",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    assert base_url is not None
    if base_url.rstrip("/") == "https://api.deepseek.com/v1":
        return "https://api.deepseek.com"
    return base_url


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: Optional[UserRead] = Depends(get_optional_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY")
    base_url = _resolve_provider_base_url(x_base_url)

    if not api_key and not (
        settings.DEPLOY_MODE == "local" and is_local_endpoint(base_url)
    ):
        raise HTTPException(status_code=401, detail="Missing API Key")

    speak_prompt = None
    if request.prompt_config:
        speak_prompt = (
            f"[角色设定]\n{request.prompt_config.persona}\n\n"
            f"[语气风格]\n{request.prompt_config.tone}\n\n"
            f"[行为准则]\n{request.prompt_config.rules}"
        )

    formatted_messages = []
    for msg in request.messages:
        if msg.role != "system":
            formatted_messages.append(msg.model_dump())

    thread_scope = _resolve_chat_thread(user, request.thread_id)

    async def stream_generator():
        stream_started = time.perf_counter()
        sequence = 0
        workflow: Optional[ChatWorkflow] = None
        try:
            # Send a first SSE frame before workflow setup or the model request.
            # This flushes the response immediately and prevents the client from
            # looking frozen while an upstream provider is connecting.
            yield format_sse(event="thinking_start", data={"type": "thinking_start"})
            workflow = ChatWorkflow(
                api_key=api_key, base_url=base_url, store=_store)

            adapter = LangGraphAdapter(workflow)
            runtime = AgentRuntime(adapter, trace_store=_trace_store)

            await workflow._ensure_checkpointer()
            checkpointer = workflow.checkpointer

            memory = _get_or_create_memory(api_key, base_url)
            memory.checkpointer = checkpointer
            workflow.memory = memory

            goal = next(
                (
                    message.get("content", "")
                    for message in reversed(formatted_messages)
                    if message.get("role") == "user"
                ),
                "",
            )
            task = AgentTask(
                user_id=user.id if user is not None else 0,
                goal=goal,
                metadata={"thread_id": thread_scope.internal_id},
            )

            async for chunk_data in runtime.stream(
                task,
                model=request.model,
                messages=formatted_messages,
                temperature=request.temperature,
                thread_id=thread_scope.internal_id,
                speak_prompt=speak_prompt,
                deepseek_options=request.deepseek_options.model_dump() if request.deepseek_options else None,
            ):
                event_type = chunk_data.get("type", "message")
                sequence += 1
                diagnostic_data = {
                    **chunk_data,
                    "stream_sequence": sequence,
                    "server_elapsed_ms": round(
                        (time.perf_counter() - stream_started) * 1000, 1
                    ),
                }
                if thread_scope.public_id is not None:
                    diagnostic_data["thread_id"] = thread_scope.public_id
                yield format_sse(event=event_type, data=diagnostic_data)

            if user is not None:
                await memory.extract_and_store_facts(thread_scope.internal_id)

        except Exception as e:
            yield format_sse(event="error", data={"detail": str(e)})
        finally:
            if workflow is not None:
                await workflow.close()

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/history")
async def get_chat_history(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = _resolve_provider_base_url(x_base_url)

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    try:
        await workflow._ensure_checkpointer()
        config = {"configurable": {"thread_id": thread_scope.internal_id, "checkpoint_ns": ""}}
        cp = await workflow.checkpointer.aget_tuple(config)

        messages = []
        if cp:
            channel_values = cp.checkpoint.get("channel_values", {})
            raw = channel_values.get("messages", [])
            for m in raw:
                if hasattr(m, "type") and hasattr(m, "content"):
                    messages.append({
                        "role": m.type,
                        "content": str(m.content),
                    })

        return {"messages": messages}
    finally:
        await workflow.close()


@router.get("/chat/reasoning/{thread_id}")
async def get_chat_reasoning(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = _resolve_provider_base_url(x_base_url)

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    try:
        await workflow._ensure_checkpointer()
        config = {"configurable": {"thread_id": thread_scope.internal_id, "checkpoint_ns": ""}}
        cp = await workflow.checkpointer.aget_tuple(config)

        if not cp:
            raise HTTPException(status_code=404, detail="Thread not found")

        channel_values = cp.checkpoint.get("channel_values", {})
        reasoning = channel_values.get("reasoning_trace", "")

        return {"thread_id": thread_id, "reasoning_trace": reasoning}
    finally:
        await workflow.close()


@router.delete("/chat/history/{thread_id}")
async def delete_chat_history(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = _resolve_provider_base_url(x_base_url)

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    try:
        await workflow._ensure_checkpointer()
        await workflow.checkpointer.adelete_thread(thread_scope.internal_id)
        return {"status": "deleted", "thread_id": thread_id}
    finally:
        await workflow.close()


@router.post("/chat/resume")
async def resume_chat(
    thread_id: str = Query(...),
    decision: str = Query("approve"),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = _resolve_provider_base_url(x_base_url)

    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url, enable_interrupt=True)
    try:
        await workflow._ensure_checkpointer()
    except Exception:
        await workflow.close()
        raise
    config = {"configurable": {"thread_id": thread_scope.internal_id, "checkpoint_ns": ""}}

    from langgraph.types import Command

    async def resume_generator():
        try:
            async for event in workflow.app.astream_events(
                Command(resume=decision),
                config=config,
                version="v2",
            ):
                kind = event["event"]
                node_name = event.get("metadata", {}).get("langgraph_node")

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        yield format_sse(event="message_chunk", data={"type": "message_chunk", "content": chunk.content})

                elif kind == "on_chat_model_end":
                    if node_name in ("speak", None):
                        yield format_sse(event="message_end", data={"type": "message_end"})

        except Exception as e:
            yield format_sse(event="error", data={"detail": str(e)})
        finally:
            await workflow.close()

    return StreamingResponse(resume_generator(), media_type="text/event-stream")


@router.get("/chat/threads")
async def list_chat_threads(
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = _resolve_provider_base_url(x_base_url)

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    try:
        await workflow._ensure_checkpointer()
        checkpoints = [c async for c in workflow.checkpointer.alist(None)]
        prefix = user_thread_prefix(user.id)
        thread_ids = list(dict.fromkeys(
            public_id
            for c in checkpoints
            for internal_id in [c.config["configurable"].get("thread_id", "")]
            if internal_id.startswith(prefix)
            for public_id in [public_thread_id(user.id, internal_id)]
            if public_id is not None
        ))
        return {"threads": thread_ids}
    finally:
        await workflow.close()


@router.get("/models/check")
async def check_connection(
    provider: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint")
):
    try:
        base_url = _resolve_provider_base_url(x_base_url)
        if provider == "ollama":
            if not base_url:
                raise HTTPException(status_code=422, detail="Ollama endpoint is required")
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    return {"status": "ok"}

        client = AsyncOpenAI(api_key=x_api_key, base_url=base_url)
        await client.models.list()
        return {"status": "ok", "message": "Connection successful"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
