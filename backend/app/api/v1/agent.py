import os
import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.agent import ChatRequest
from app.schemas.collection import CollectionSearchBase
from app.schemas.user import UserRead
from app.agents.graph import ChatWorkflow
from app.agents.langgraph_adapter import LangGraphAdapter
from app.agents.agent_registry import AgentRegistry
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.router import AgentRouter
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.anime import AnimeCapability
from app.harness.runtime import AgentRuntime
from app.harness.budget import CancellationToken
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.model_gateway import OpenAICompatibleModelAdapter, OpenAIModelGateway
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import InvalidRunTransition, RunStore
from app.harness.routing_adapter import FeatureFlagRoutingAdapter
from app.harness.task import AgentTask
from app.memory.service import MemoryServiceImpl
from app.memory.sql_repository import SqlMemoryRepository
from app.memory.extractor import LLMFactExtractor
from app.services.collection_service import get_user_collections
from app.api.deps import get_current_user, get_optional_user
from app.db.database import get_session
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

from app.trace.sql_store import SqlTraceStore
from app.models.agent_run import AgentRunEvent

router = APIRouter()

_store = InMemoryStore()


_TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
_MAX_REPLAY_CURSOR = 1_000_000_000


def _interactive_run_store_enabled() -> bool:
    return os.getenv("INTERACTIVE_RUN_STORE_ENABLED", "true").lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _checkpoint_adapter_enabled() -> bool:
    return settings.HARNESS_CHECKPOINT_ADAPTER.lower() not in {
        "legacy",
        "off",
        "disabled",
    }


async def _latest_thread_checkpoint(checkpointer, thread_id: str):
    """Read the newest checkpoint across legacy and run-scoped namespaces."""
    config = {"configurable": {"thread_id": thread_id}}
    async for checkpoint in checkpointer.alist(config, limit=1):
        return checkpoint
    return None


def format_sse(event: str, data: dict, *, event_id: int | str | None = None) -> str:
    identifier = f"id: {event_id}\n" if event_id is not None else ""
    return (
        f"{identifier}event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def _parse_replay_cursor(after: str | None, last_event_id: str | None) -> int:
    raw_value = after if after is not None else last_event_id
    if raw_value in (None, ""):
        return 0
    try:
        cursor = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid event cursor") from exc
    if cursor < 0 or cursor > _MAX_REPLAY_CURSOR:
        raise HTTPException(status_code=400, detail="event cursor out of range")
    return cursor


async def _get_scoped_run(
    run_id: str,
    user: UserRead,
    thread_id: Optional[str],
    db: AsyncSession,
):
    run = await RunStore(db).get(run_id, user_id=user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if thread_id is not None:
        try:
            expected_thread = _resolve_user_thread(user, thread_id).internal_id
        except HTTPException:
            raise HTTPException(status_code=404, detail="Run not found") from None
        if run.thread_id != expected_thread:
            raise HTTPException(status_code=404, detail="Run not found")
    return await _recover_stale_run(run, db)


async def _recover_stale_run(run, db: AsyncSession):
    """Fail closed after a single-worker lease has clearly expired.

    AgentRun has no separate lease column by design in this batch. The start
    timestamp is therefore a conservative local-development lease boundary;
    production shared-worker coordination remains an adapter concern.
    """
    lease_seconds = settings.CHECKPOINT_LEASE_SECONDS
    started_at = run.started_at
    if (
        run.status != "running"
        or started_at is None
        or lease_seconds <= 0
    ):
        return run
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
    if age_seconds <= lease_seconds:
        return run

    run_store = RunStore(db)
    try:
        recovered = await run_store.transition(
            run.run_id,
            "abandoned",
            error_code="checkpoint_lease_expired",
        )
    except InvalidRunTransition:
        recovered = await run_store.get(run.run_id, user_id=run.user_id)
        if recovered is None:
            raise HTTPException(status_code=404, detail="Run not found") from None
        return recovered
    if _checkpoint_adapter_enabled():
        checkpoint_store = SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
        await checkpoint_store.mark_abandoned(
            run.run_id,
            "checkpoint lease expired during service recovery",
        )
    return recovered


async def _last_event_sequence(run_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        sa_select(func.max(AgentRunEvent.sequence)).where(
            AgentRunEvent.run_id == run_id
        )
    )
    return int(result.scalar_one() or 0)


def _serialize_run_event(event: AgentRunEvent) -> dict:
    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "invocation_id": event.invocation_id,
        "payload": event.payload,
        "occurred_at": event.occurred_at.isoformat(),
    }


@router.get("/runs/{run_id}")
async def get_run_projection(
    run_id: str,
    thread_id: Optional[str] = Query(None),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    run = await _get_scoped_run(run_id, user, thread_id, db)
    return {
        "run_id": run.run_id,
        "status": run.status,
        "last_sequence": await _last_event_sequence(run_id, db),
        "error_code": run.error_code,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("/runs/{run_id}/events")
async def get_run_events_projection(
    run_id: str,
    after: Optional[str] = Query(None),
    thread_id: Optional[str] = Query(None),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    cursor = _parse_replay_cursor(after, last_event_id)
    await _get_scoped_run(run_id, user, thread_id, db)
    events = await EventStore(db).list_after(run_id, after_sequence=cursor)
    return {
        "run_id": run_id,
        "after": cursor,
        "events": [_serialize_run_event(event) for event in events],
    }


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
    db: AsyncSession = Depends(get_session),
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
    run_id = uuid4().hex
    durable_run = user is not None and _interactive_run_store_enabled()
    cancellation = CancellationToken()

    async def stream_generator():
        stream_started = time.perf_counter()
        sequence = 0
        workflow: Optional[ChatWorkflow] = None
        checkpoint_store: Optional[SqliteCheckpointStore] = None
        try:
            # Send a first SSE frame before workflow setup or the model request.
            # This flushes the response immediately and prevents the client from
            # looking frozen while an upstream provider is connecting.
            initial_data = {"type": "thinking_start"}
            if durable_run:
                initial_data["run_id"] = run_id
            yield format_sse(
                event="thinking_start",
                data=initial_data,
                event_id=1 if durable_run else None,
            )
            workflow = ChatWorkflow(
                api_key=api_key,
                base_url=base_url,
                store=_store,
                checkpoint_path=settings.CHECKPOINT_DB_PATH,
                run_id=run_id,
                thread_id=thread_scope.internal_id,
                cancellation=cancellation,
            )

            await workflow._ensure_checkpointer()
            checkpointer = workflow.checkpointer

            memory = None
            collections: list = []
            if user is not None:
                memory = MemoryServiceImpl(
                    repository=SqlMemoryRepository(db),
                    extractor=LLMFactExtractor(
                        api_key=api_key,
                        base_url=base_url,
                    ),
                    api_key=api_key,
                    base_url=base_url,
                    checkpointer=checkpointer,
                    default_user_id=user.id,
                )
                workflow.memory = memory
                if settings.ENABLE_MULTI_AGENT_ROUTING:
                    try:
                        collection_list = await get_user_collections(
                            db,
                            CollectionSearchBase(user_id=user.id, limit=100),
                        )
                        collections = collection_list.items
                    except Exception:
                        collections = []

            fallback_adapter = LangGraphAdapter(workflow)
            registry = AgentRegistry()
            registry.register(
                "recommendation",
                RecommendationAgent(
                    RecommendationCapability(),
                    anime_capability=AnimeCapability(),
                    memory_service=memory,
                ),
            )
            adapter = FeatureFlagRoutingAdapter(
                fallback_adapter,
                AgentRouter(registry),
                enabled=settings.ENABLE_MULTI_AGENT_ROUTING,
            )
            checkpoint_store = (
                SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
                if durable_run and _checkpoint_adapter_enabled()
                else None
            )
            model_gateway = OpenAIModelGateway(
                api_key=api_key,
                base_url=base_url,
                model=request.model,
                temperature=request.temperature,
                deepseek_options=(
                    request.deepseek_options.model_dump()
                    if request.deepseek_options
                    else None
                ),
            )
            runtime = AgentRuntime(
                adapter,
                checkpoint_store=checkpoint_store,
                trace_store=SqlTraceStore(db),
                model_gateway=model_gateway,
                run_store=RunStore(db) if durable_run else None,
                event_store=EventStore(db) if durable_run else None,
            )

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
                metadata={
                    "thread_id": thread_scope.internal_id,
                    "messages": formatted_messages,
                    "collections": collections,
                    "run_id": run_id,
                },
            )

            async for chunk_data in runtime.stream(
                task,
                model=request.model,
                messages=formatted_messages,
                temperature=request.temperature,
                thread_id=thread_scope.internal_id,
                speak_prompt=speak_prompt,
                deepseek_options=request.deepseek_options.model_dump() if request.deepseek_options else None,
                cancellation=cancellation,
            ):
                event_type = chunk_data.get("type", "message")
                sequence += 1
                durable_sequence = (
                    await _last_event_sequence(run_id, db)
                    if durable_run
                    else None
                )
                diagnostic_data = {
                    **chunk_data,
                    "stream_sequence": sequence,
                    "server_elapsed_ms": round(
                        (time.perf_counter() - stream_started) * 1000, 1
                    ),
                }
                if thread_scope.public_id is not None:
                    diagnostic_data["thread_id"] = thread_scope.public_id
                if durable_run:
                    diagnostic_data["run_id"] = run_id
                yield format_sse(
                    event=event_type,
                    data=diagnostic_data,
                    event_id=durable_sequence if durable_run else None,
                )

            if durable_run:
                stored_run = await RunStore(db).get(run_id, user_id=user.id)
                if stored_run is not None and stored_run.status in _TERMINAL_RUN_STATUSES:
                    last_sequence = await _last_event_sequence(run_id, db)
                    yield format_sse(
                        event="run_status",
                        data={
                            "type": "run_status",
                            "run_id": run_id,
                            "status": stored_run.status,
                            "error_code": stored_run.error_code,
                            "last_sequence": last_sequence,
                        },
                        event_id=last_sequence or None,
                    )

            if memory is not None and user is not None:
                await memory.extract_and_store_facts(
                    thread_scope.internal_id,
                    user_id=user.id,
                )

        except Exception as e:
            yield format_sse(event="error", data={"detail": str(e)})
        finally:
            if workflow is not None:
                await workflow.close()
            if checkpoint_store is not None:
                await checkpoint_store.close()

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

    workflow = ChatWorkflow(
        api_key=api_key,
        base_url=base_url,
        checkpoint_path=settings.CHECKPOINT_DB_PATH,
    )
    try:
        await workflow._ensure_checkpointer()
        cp = await _latest_thread_checkpoint(
            workflow.checkpointer,
            thread_scope.internal_id,
        )

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

    workflow = ChatWorkflow(
        api_key=api_key,
        base_url=base_url,
        checkpoint_path=settings.CHECKPOINT_DB_PATH,
    )
    try:
        await workflow._ensure_checkpointer()
        cp = await _latest_thread_checkpoint(
            workflow.checkpointer,
            thread_scope.internal_id,
        )

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

    workflow = ChatWorkflow(
        api_key=api_key,
        base_url=base_url,
        checkpoint_path=settings.CHECKPOINT_DB_PATH,
    )
    try:
        await workflow._ensure_checkpointer()
        await workflow.checkpointer.adelete_thread(thread_scope.internal_id)
        return {"status": "deleted", "thread_id": thread_id}
    finally:
        await workflow.close()


@router.post("/chat/resume")
async def resume_chat(
    thread_id: str = Query(...),
    run_id: Optional[str] = Query(None),
    decision: str = Query("approve"),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = _resolve_provider_base_url(x_base_url)

    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    if run_id is not None:
        run = await RunStore(db).get(run_id, user_id=user.id)
        if run is None or run.thread_id != thread_scope.internal_id:
            raise HTTPException(status_code=404, detail="Run not found")
        run = await _recover_stale_run(run, db)
        if run.status not in {"running", "paused"}:
            raise HTTPException(status_code=409, detail="Run is not resumable")

    workflow = ChatWorkflow(
        api_key=api_key,
        base_url=base_url,
        checkpoint_path=settings.CHECKPOINT_DB_PATH,
        run_id=run_id,
        thread_id=thread_scope.internal_id,
        cancellation=CancellationToken(),
        enable_interrupt=True,
    )
    try:
        await workflow._ensure_checkpointer()
    except Exception:
        await workflow.close()
        raise
    if hasattr(workflow, "_checkpoint_config"):
        config = workflow._checkpoint_config(thread_scope.internal_id, run_id)
        if run_id is None and hasattr(workflow.checkpointer, "alist"):
            latest = await _latest_thread_checkpoint(
                workflow.checkpointer,
                thread_scope.internal_id,
            )
            if latest is not None:
                config = latest.config
    else:
        config = {
            "configurable": {
                "thread_id": thread_scope.internal_id,
                "checkpoint_ns": "",
            }
        }
        if run_id is not None:
            config["metadata"] = {"run_id": run_id}

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

    workflow = ChatWorkflow(
        api_key=api_key,
        base_url=base_url,
        checkpoint_path=settings.CHECKPOINT_DB_PATH,
    )
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

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=x_api_key, base_url=base_url)
        result = await OpenAICompatibleModelAdapter(
            client,
            provider="openai-compatible",
        ).check_connection()
        if result.status == "completed":
            return {"status": "ok", "message": "Connection successful"}
        detail = {
            "auth": "Provider authentication failed",
            "rate_limited": "Provider rate limit reached",
            "timeout": "Provider request timed out",
            "invalid_request": "Provider request was invalid",
            "transient": "Provider temporarily unavailable",
            "cancelled": "Provider request was cancelled",
        }.get(result.error_code, "Provider connection failed")
        raise HTTPException(status_code=400, detail=detail)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Provider connection failed")
