import os
import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Optional
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
from app.capabilities.factory import build_capability_registry
from app.harness.runtime import AgentRuntime
from app.harness.budget import CancellationToken, RunBudget
from app.harness.cancellation_store import cancellation_store
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import ErrorCode, ExecutionContext, RunEvent
from app.harness.decision_parser import DecisionParseError, DecisionParser
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import (
    OpenAICompatibleModelAdapter,
    OpenAIModelGateway,
    safe_provider_detail,
)
from app.harness.model_types import ModelCallResult
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
    ProviderEndpointError,
    ProviderEndpointPolicy,
    create_provider_http_client,
    is_local_endpoint,
    make_provider_endpoint_policy,
    parse_provider_allowlists,
    validate_provider_endpoint,
)
from app.core.config import settings

from app.trace.sql_store import SqlTraceStore
from app.models.agent_run import AgentRunEvent

router = APIRouter()

_store = InMemoryStore()


_TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
_MAX_REPLAY_CURSOR = 1_000_000_000
_MODEL_CHECK_ATTEMPTS: dict[int, list[float]] = {}


def _interactive_run_store_enabled() -> bool:
    return os.getenv("INTERACTIVE_RUN_STORE_ENABLED", "true").lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _primary_decision_loop_enabled() -> bool:
    """Enable the Runtime-owned chat loop by default.

    An explicit false value is retained as the narrowly-scoped rollback to the
    previously verified compatibility adapter.  It is never the production
    default and does not grant legacy code a new execution capability.
    """
    return os.getenv("HARNESS_PRIMARY_DECISION_LOOP_ENABLED", "true").lower() not in {
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
    lease_recovered = False
    if run.status == "running" and _checkpoint_adapter_enabled():
        checkpoint_store = SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
        try:
            lease_recovered = await checkpoint_store.recover_expired(
                run.run_id,
                "checkpoint lease expired during service recovery",
            )
        finally:
            await checkpoint_store.close()
    started_at = run.started_at
    if (
        run.status != "running"
        or (started_at is None and not lease_recovered)
        or lease_seconds <= 0
    ):
        return run
    if lease_recovered:
        age_seconds = lease_seconds + 1
    else:
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
    if not lease_recovered and age_seconds <= lease_seconds:
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
        try:
            await checkpoint_store.mark_abandoned(
                run.run_id,
                "checkpoint lease expired during service recovery",
            )
        finally:
            await checkpoint_store.close()
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


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    thread_id: Optional[str] = Query(None),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Request owner-scoped cancellation and persist the cancellation fact."""
    run = await _get_scoped_run(run_id, user, thread_id, db)
    if run.status in _TERMINAL_RUN_STATUSES or run.status == "abandoned":
        return {
            "run_id": run.run_id,
            "status": run.status,
            "error_code": run.error_code,
            "idempotent": True,
        }
    if run.status not in {"queued", "running", "paused"}:
        raise HTTPException(status_code=409, detail="Run is not cancellable")

    if _checkpoint_adapter_enabled():
        checkpoint_store = SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
        try:
            await checkpoint_store.request_cancellation(
                run_id,
                requester=f"user:{user.id}",
                reason="client requested cancellation",
            )
        finally:
            await checkpoint_store.close()
    cancellation_store.cancel(run_id)
    event_store = EventStore(db)
    sequence = await _last_event_sequence(run_id, db) + 1
    await event_store.append(
        RunEvent(
            run_id=run_id,
            sequence=sequence,
            event_type="run.cancel_requested",
            payload={},
        )
    )
    return {
        "run_id": run.run_id,
        "status": run.status,
        "error_code": run.error_code,
        "cancellation_requested": True,
        "last_sequence": await _last_event_sequence(run_id, db),
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


def _provider_endpoint_policy() -> ProviderEndpointPolicy:
    try:
        allowed_hosts, allowed_ports = parse_provider_allowlists(
            settings.PROVIDER_ALLOWED_HOSTS,
            settings.PROVIDER_ALLOWED_PORTS,
        )
        return make_provider_endpoint_policy(
            deploy_mode=settings.DEPLOY_MODE,
            resolve_dns=settings.PROVIDER_RESOLVE_DNS,
            allowed_hosts=allowed_hosts,
            allowed_ports=allowed_ports,
        )
    except ProviderEndpointError as exc:
        raise HTTPException(
            status_code=503,
            detail="Provider endpoint policy is not configured",
        ) from exc


def _resolve_provider_base_url(value: Optional[str]) -> str:
    policy = _provider_endpoint_policy()
    try:
        base_url = validate_provider_endpoint(
            value or "https://api.openai.com/v1",
            allow_local=policy.allow_local,
            resolve_dns=policy.resolve_dns,
            allowed_hosts=policy.allowed_hosts or None,
            allowed_ports=policy.allowed_ports or None,
            allowed_schemes=policy.allowed_schemes,
        )
    except ProviderEndpointError as exc:
        detail = (
            "Provider endpoint DNS resolution failed"
            if exc.provider_error_code == "dns"
            else "Provider endpoint is not allowed"
        )
        raise HTTPException(status_code=422, detail=detail) from exc
    assert base_url is not None
    if base_url.rstrip("/") == "https://api.deepseek.com/v1":
        return "https://api.deepseek.com"
    return base_url


def _consume_model_check_rate_limit(user: UserRead) -> bool:
    """Apply a bounded per-owner check budget before opening a provider socket."""
    limit = max(1, int(settings.MODEL_CHECK_RATE_LIMIT))
    window = max(1, int(settings.MODEL_CHECK_RATE_WINDOW_SECONDS))
    now = time.monotonic()
    attempts = [
        timestamp
        for timestamp in _MODEL_CHECK_ATTEMPTS.get(user.id, [])
        if now - timestamp < window
    ]
    if len(attempts) >= limit:
        _MODEL_CHECK_ATTEMPTS[user.id] = attempts
        return False
    attempts.append(now)
    _MODEL_CHECK_ATTEMPTS[user.id] = attempts
    return True


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
    goal = next(
        (
            message.get("content", "")
            for message in reversed(formatted_messages)
            if message.get("role") == "user"
        ),
        "",
    )
    durable_run = user is not None and _interactive_run_store_enabled()
    cancellation = CancellationToken()
    cancellation_store.register(run_id, cancellation)

    async def stream_generator():
        stream_started = time.perf_counter()
        sequence = 0
        primary_decision_loop = _primary_decision_loop_enabled()
        workflow: Optional[ChatWorkflow] = None
        checkpointer = None
        checkpoint_store: Optional[SqliteCheckpointStore] = None
        dispatcher: Optional[Dispatcher] = None
        model_gateway: Optional[OpenAIModelGateway] = None
        try:
            # The legacy adapter needs an early flush before workflow setup.
            # The Runtime-owned Decision Loop emits its own canonical
            # ``thinking_start`` event, so do not duplicate it here.
            if not primary_decision_loop:
                initial_data = {"type": "thinking_start"}
                if durable_run:
                    initial_data["run_id"] = run_id
                yield format_sse(
                    event="thinking_start",
                    data=initial_data,
                    event_id=1 if durable_run else None,
                )
            capability_registry = build_capability_registry()
            dispatcher = Dispatcher(capability_registry)
            execution_context = ExecutionContext(
                principal_id=user.id if user is not None else None,
                run_id=run_id,
                trace_id=run_id,
                capability_allowlist=frozenset(
                    definition.public_name
                    for definition in capability_registry.allowed_public_definitions()
                ),
            )
            decision_parser = DecisionParser()

            if not primary_decision_loop:
                async def dispatch_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
                    try:
                        decision = decision_parser.parse(
                            ModelCallResult(
                                provider="langgraph",
                                model=request.model,
                                operation="decision",
                                status="completed",
                                decision=proposal,
                            ),
                            expected_run_id=run_id,
                        )
                        invocation = await dispatcher.dispatch(
                            decision,
                            execution_context,
                            cancellation=cancellation,
                        )
                        return {
                            "success": invocation.status == "succeeded",
                            "decision": proposal,
                            "invocation_id": invocation.invocation_id,
                            "status": invocation.status,
                            "output": invocation.output,
                            "error_type": (
                                invocation.error_code.value
                                if isinstance(invocation.error_code, ErrorCode)
                                else invocation.error_code
                            ),
                        }
                    except DecisionParseError as exc:
                        return {
                            "success": False,
                            "decision": proposal,
                            "status": "denied",
                            "error_type": exc.error_code.value,
                            "message": "Model decision was invalid",
                        }

                workflow = ChatWorkflow(
                    api_key=api_key,
                    base_url=base_url,
                    store=_store,
                    checkpoint_path=settings.CHECKPOINT_DB_PATH,
                    run_id=run_id,
                    thread_id=thread_scope.internal_id,
                    cancellation=cancellation,
                    proposal_handler=dispatch_proposal,
                )
                await workflow._ensure_checkpointer()
                checkpointer = workflow.checkpointer

            memory = None
            memory_context = None
            collections: list = []
            model_gateway = OpenAIModelGateway(
                api_key=api_key,
                base_url=base_url,
                model=request.model,
                temperature=request.temperature,
                endpoint_policy=_provider_endpoint_policy(),
                deepseek_options=(
                    request.deepseek_options.model_dump()
                    if request.deepseek_options
                    else None
                ),
            )
            if user is not None:
                memory = MemoryServiceImpl(
                    repository=SqlMemoryRepository(db),
                    extractor=LLMFactExtractor(
                        api_key=api_key,
                        base_url=base_url,
                        model_gateway=model_gateway,
                    ),
                    api_key=api_key,
                    base_url=base_url,
                    checkpointer=checkpointer,
                    default_user_id=user.id,
                    run_id=run_id,
                )
                if workflow is not None:
                    workflow.memory = memory
                if primary_decision_loop:
                    memory_context = await memory.retrieve_context(
                        thread_scope.internal_id,
                        goal,
                        user_id=user.id,
                        run_id=run_id,
                    )
                if settings.ENABLE_MULTI_AGENT_ROUTING:
                    try:
                        collection_list = await get_user_collections(
                            db,
                            CollectionSearchBase(user_id=user.id, limit=100),
                        )
                        collections = collection_list.items
                    except Exception:
                        collections = []

            if workflow is not None:
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
                    # The compatibility route remains explicitly disabled;
                    # enabled specialist execution fails closed until it has
                    # a Dispatcher-backed subagent contract.
                    enabled=False,
                )
            else:
                # stream_decision is Runtime-owned and never consults the
                # compatibility adapter.  Keep the constructor explicit for
                # tracing while avoiding any LangGraph graph compilation.
                adapter = object()
            checkpoint_store = (
                SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
                if durable_run and _checkpoint_adapter_enabled()
                else None
            )
            run_budget = RunBudget()
            runtime = AgentRuntime(
                adapter,
                checkpoint_store=checkpoint_store,
                trace_store=SqlTraceStore(db),
                model_gateway=model_gateway,
                dispatcher=dispatcher,
                run_store=RunStore(db) if durable_run else None,
                event_store=EventStore(db) if durable_run else None,
                memory_context=memory_context,
                memory_service=memory,
                checkpoint_lease_seconds=settings.CHECKPOINT_LEASE_SECONDS,
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

            if primary_decision_loop:
                stream_iterator = runtime.stream_decision(
                    task,
                    context=execution_context,
                    budget=run_budget,
                    cancellation=cancellation,
                )
            else:
                stream_iterator = runtime.stream(
                    task,
                    model=request.model,
                    messages=formatted_messages,
                    temperature=request.temperature,
                    thread_id=thread_scope.internal_id,
                    speak_prompt=speak_prompt,
                    deepseek_options=request.deepseek_options.model_dump() if request.deepseek_options else None,
                    budget=run_budget,
                    cancellation=cancellation,
                )

            async for chunk_data in stream_iterator:
                event_type = chunk_data.get("type", "message")
                if durable_run and primary_decision_loop:
                    # The primary Runtime has already committed this exact
                    # event to EventStore.  SSE is only its safe projection;
                    # do not add diagnostics or allocate a second sequence.
                    yield format_sse(
                        event=event_type,
                        data=chunk_data,
                        event_id=chunk_data.get("sequence"),
                    )
                    continue
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

            if durable_run and not primary_decision_loop:
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

        except Exception:
            yield format_sse(
                event="error",
                data={
                    "error_code": "internal_error",
                    "detail": "Agent run failed",
                },
            )
        finally:
            cancellation_store.unregister(run_id, cancellation)
            if workflow is not None:
                await workflow.close()
            if checkpoint_store is not None:
                await checkpoint_store.close()
            if model_gateway is not None:
                await model_gateway.close()

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

    if _primary_decision_loop_enabled():
        raise HTTPException(
            status_code=409,
            detail="Runtime-owned approval resume is not available through the legacy Workflow adapter",
        )

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

        except Exception:
            yield format_sse(
                event="error",
                data={
                    "error_code": "internal_error",
                    "detail": "Agent run failed",
                },
            )
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
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    if not _consume_model_check_rate_limit(user):
        raise HTTPException(
            status_code=429,
            detail="Provider check rate limit reached",
            headers={"Retry-After": str(settings.MODEL_CHECK_RATE_WINDOW_SECONDS)},
        )
    if provider not in {"ollama", "openai-compatible", "deepseek"}:
        raise HTTPException(status_code=422, detail="Unsupported provider")

    try:
        base_url = _resolve_provider_base_url(x_base_url)
        policy = _provider_endpoint_policy()
        if provider == "ollama":
            async with create_provider_http_client(policy, timeout=5.0) as client:
                resp = await client.get(f"{base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    return {"status": "ok"}
                if resp.status_code in {401, 403}:
                    detail = "Provider authentication failed"
                elif resp.status_code == 429:
                    detail = "Provider rate limit reached"
                elif resp.status_code >= 500:
                    detail = "Provider temporarily unavailable"
                else:
                    detail = "Provider connection failed"
                raise HTTPException(status_code=400, detail=detail)

        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=x_api_key or settings.OPENAI_API_KEY or "local",
            base_url=base_url,
            timeout=5.0,
            http_client=create_provider_http_client(policy, timeout=5.0),
        )
        try:
            result = await OpenAICompatibleModelAdapter(
                client,
                provider=provider,
            ).check_connection()
        finally:
            await client.close()
        if result.status == "completed":
            return {"status": "ok", "message": "Connection successful"}
        detail = {
            "auth": "Provider authentication failed",
            "rate_limited": "Provider rate limit reached",
            "timeout": "Provider request timed out",
            "invalid_request": "Provider request was invalid",
            "transient": "Provider temporarily unavailable",
            "cancelled": "Provider request was cancelled",
            "dns": "Provider DNS resolution failed",
            "ssrf": "Provider endpoint is not allowed",
        }.get(result.error_code, "Provider connection failed")
        raise HTTPException(status_code=400, detail=detail)

    except HTTPException:
        raise
    except ProviderEndpointError as exc:
        detail = (
            "Provider endpoint DNS resolution failed"
            if exc.provider_error_code == "dns"
            else "Provider endpoint is not allowed"
        )
        raise HTTPException(status_code=422, detail=detail) from exc
    except (httpx.TimeoutException, TimeoutError):
        raise HTTPException(status_code=400, detail="Provider request timed out")
    except Exception as exc:
        # Do not return raw provider/client exception details to the caller.
        raise HTTPException(status_code=400, detail=safe_provider_detail(exc)) from exc
