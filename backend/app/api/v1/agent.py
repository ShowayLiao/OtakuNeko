import os
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
from openai import AsyncOpenAI
from langgraph.store.memory import InMemoryStore
from app.schemas.agent import ChatRequest
from app.schemas.user import UserRead
from app.agents.graph import ChatWorkflow
from app.memory.manager import MemoryManager
from app.api.deps import get_current_user, get_optional_user

router = APIRouter()

_store = InMemoryStore()
_memory_managers: dict[tuple, MemoryManager] = {}


def _get_or_create_memory(api_key: str, base_url: str) -> MemoryManager:
    key = (api_key, base_url)
    if key not in _memory_managers:
        _memory_managers[key] = MemoryManager(
            api_key=api_key, base_url=base_url, store=_store)
    return _memory_managers[key]


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: Optional[UserRead] = Depends(get_optional_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY")
    base_url = x_base_url or "https://api.openai.com/v1"

    if not api_key and "localhost" not in base_url:
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

    async def stream_generator():
        try:
            workflow = ChatWorkflow(
                api_key=api_key, base_url=base_url, store=_store)

            await workflow._ensure_checkpointer()
            checkpointer = workflow.checkpointer

            memory = _get_or_create_memory(api_key, base_url)
            memory.checkpointer = checkpointer
            workflow.memory = memory

            thread_id = request.thread_id or "default"

            async for chunk_data in workflow.stream_chat(
                model=request.model,
                messages=formatted_messages,
                temperature=request.temperature,
                thread_id=thread_id,
                speak_prompt=speak_prompt,
            ):
                event_type = chunk_data.get("type", "message")
                yield format_sse(event=event_type, data=chunk_data)

            if thread_id and user is not None and thread_id != "default":
                asyncio.create_task(memory.extract_and_store_facts(thread_id))

        except Exception as e:
            yield format_sse(event="error", data={"detail": str(e)})

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/chat/history")
async def get_chat_history(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = x_base_url or "https://api.openai.com/v1"

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    await workflow._ensure_checkpointer()
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
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


@router.get("/chat/reasoning/{thread_id}")
async def get_chat_reasoning(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = x_base_url or "https://api.openai.com/v1"

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    await workflow._ensure_checkpointer()
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    cp = await workflow.checkpointer.aget_tuple(config)

    if not cp:
        raise HTTPException(status_code=404, detail="Thread not found")

    channel_values = cp.checkpoint.get("channel_values", {})
    reasoning = channel_values.get("reasoning_trace", "")

    return {"thread_id": thread_id, "reasoning_trace": reasoning}


@router.delete("/chat/history/{thread_id}")
async def delete_chat_history(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = x_base_url or "https://api.openai.com/v1"

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    await workflow._ensure_checkpointer()
    await workflow.checkpointer.adelete_thread(thread_id)
    return {"status": "deleted", "thread_id": thread_id}


@router.post("/chat/resume")
async def resume_chat(
    thread_id: str = Query(...),
    decision: str = Query("approve"),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = x_base_url or "https://api.openai.com/v1"

    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url, enable_interrupt=True)
    await workflow._ensure_checkpointer()
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

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

    return StreamingResponse(resume_generator(), media_type="text/event-stream")


@router.get("/chat/threads")
async def list_chat_threads(
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = x_base_url or "https://api.openai.com/v1"

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    await workflow._ensure_checkpointer()
    checkpoints = [c async for c in workflow.checkpointer.alist(None)]
    thread_ids = list(dict.fromkeys(
        c.config["configurable"]["thread_id"]
        for c in checkpoints
    ))
    return {"threads": thread_ids}


@router.get("/models/check")
async def check_connection(
    provider: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint")
):
    try:
        if provider == "ollama":
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{x_base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    return {"status": "ok"}

        client = AsyncOpenAI(api_key=x_api_key, base_url=x_base_url)
        await client.models.list()
        return {"status": "ok", "message": "Connection successful"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
