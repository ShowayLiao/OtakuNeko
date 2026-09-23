import os
import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.agent import ChatRequest
from app.schemas.user import UserRead
from app.capabilities.factory import build_capability_registry
from app.harness.runtime import AgentRuntime
from app.harness.budget import CancellationToken, RunBudget
from app.harness.cancellation_store import cancellation_store
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import ExecutionContext, RunEvent
from app.harness.dispatcher import Dispatcher
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.model_gateway import (
    OpenAICompatibleModelAdapter,
    OpenAIModelGateway,
    safe_provider_detail,
)
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import InvalidRunTransition, RunStore
from app.harness.policy import Approval, PolicyEngine
from app.harness.task import AgentTask
from app.memory.service import MemoryServiceImpl
from app.memory.sql_repository import SqlMemoryRepository
from app.memory.extractor import LLMFactExtractor
from app.api.deps import get_current_user, get_optional_user
from app.db.database import get_session
from app.agents.agent_registry import AgentRegistry
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.router import AgentRouter
from app.agents.thread_scope import (
    make_anonymous_thread,
    make_user_thread,
    public_thread_id,
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


def _checkpoint_adapter_enabled() -> bool:
    return settings.HARNESS_CHECKPOINT_ADAPTER.lower() not in {
        "legacy",
        "off",
        "disabled",
    }


def format_sse(event: str, data: dict, *, event_id: int | str | None = None) -> str:
    identifier = f"id: {event_id}\n" if event_id is not None else ""
    return (
        f"{identifier}event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def _capability_adapter_factory(
    *,
    db: AsyncSession,
    user: UserRead | None,
    policy_engine: PolicyEngine,
    approval: Approval | None,
    idempotency_store: Any | None,
):
    """Build adapters with trusted request dependencies, never model arguments."""
    def factory(capability: Any) -> CapabilityAdapter:
        capability_name = getattr(capability, "name", "")
        trusted_args: dict[str, Any] = {}
        if capability_name in {
            "collections", "subjects", "stats", "schedule", "recommendation"
        }:
            trusted_args["db"] = db
        if user is not None and capability_name in {"collections", "anime"}:
            trusted_args["user"] = user
        return CapabilityAdapter(
            capability,
            policy_engine=policy_engine,
            approval=approval,
            idempotency_store=idempotency_store,
            trusted_args=trusted_args,
        )

    return factory


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


def _chat_sse_projection(data: dict[str, Any], *, durable: bool) -> dict[str, Any]:
    """Add transport metadata without changing the Runtime event fact."""
    return {**data, "durable": durable}


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
    if speak_prompt:
        formatted_messages.insert(0, {"role": "system", "content": speak_prompt})

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
        checkpoint_store: Optional[SqliteCheckpointStore] = None
        dispatcher: Optional[Dispatcher] = None
        model_gateway: Optional[OpenAIModelGateway] = None
        try:
            capability_registry = build_capability_registry()
            policy_engine = PolicyEngine(allow_side_effects=True)
            idempotency_store = SqlIdempotencyStore(db) if durable_run else None
            dispatcher = Dispatcher(
                capability_registry,
                policy_engine=policy_engine,
                idempotency_store=idempotency_store,
                adapter_factory=_capability_adapter_factory(
                    db=db,
                    user=user,
                    policy_engine=policy_engine,
                    approval=None,
                    idempotency_store=idempotency_store,
                ),
            )
            execution_context = ExecutionContext(
                principal_id=user.id if user is not None else None,
                run_id=run_id,
                trace_id=run_id,
                capability_allowlist=frozenset(
                    definition.public_name
                    for definition in capability_registry.allowed_public_definitions(
                        include_side_effects=user is not None
                    )
                ),
                thread_id=thread_scope.internal_id,
            )

            memory = None
            memory_context = None
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
                    default_user_id=user.id,
                    run_id=run_id,
                )
                memory_context = await memory.retrieve_context(
                    thread_scope.internal_id,
                    goal,
                    user_id=user.id,
                    run_id=run_id,
                )

            specialist_router: AgentRouter | None = None
            if settings.ENABLE_MULTI_AGENT_ROUTING:
                recommendation_owner = capability_registry.find_action(
                    "generate_user_profile_tool"
                )
                anime_owner = capability_registry.find_action("search_anime_advanced")
                if recommendation_owner is not None and anime_owner is not None:
                    agent_registry = AgentRegistry()
                    agent_registry.register(
                        "recommendation",
                        RecommendationAgent(
                            recommendation_owner[0],
                            anime_capability=anime_owner[0],
                            memory_service=memory,
                        ),
                    )
                    specialist_router = AgentRouter(agent_registry)

            # The structured Decision loop is controlled by AgentRuntime and
            # does not require a separate adapter or graph object.
            checkpoint_store = (
                SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
                if durable_run and _checkpoint_adapter_enabled()
                else None
            )
            run_budget = RunBudget()
            runtime = AgentRuntime(
                checkpoint_store=checkpoint_store,
                trace_store=SqlTraceStore(db),
                model_gateway=model_gateway,
                dispatcher=dispatcher,
                specialist_router=specialist_router,
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
                    "run_id": run_id,
                    "model": request.model,
                },
            )

            stream_iterator = runtime.stream_decision(
                task,
                context=execution_context,
                budget=run_budget,
                cancellation=cancellation,
            )

            async for chunk_data in stream_iterator:
                event_type = chunk_data.get("type", "message")
                diagnostic_data = _chat_sse_projection(chunk_data, durable=durable_run)
                if thread_scope.public_id is not None:
                    diagnostic_data["thread_id"] = thread_scope.public_id
                if durable_run:
                    diagnostic_data["run_id"] = run_id
                yield format_sse(
                    event=event_type,
                    data=diagnostic_data,
                    event_id=chunk_data.get("sequence") if durable_run else None,
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
    db: AsyncSession = Depends(get_session),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    runs = await RunStore(db).list_for_thread(
        thread_scope.internal_id,
        user_id=user.id,
    )
    events = await EventStore(db).list_for_runs([run.run_id for run in runs])
    messages: list[dict[str, str]] = []
    for event in events:
        if event.event_type == "message_input":
            content = event.payload.get("content")
            if isinstance(content, str):
                messages.append({"role": "user", "content": content})
        elif event.event_type == "message_chunk":
            content = event.payload.get("content")
            if not isinstance(content, str):
                continue
            if messages and messages[-1]["role"] == "assistant":
                messages[-1]["content"] += content
            else:
                messages.append({"role": "assistant", "content": content})
    return {"messages": messages}


@router.get("/chat/reasoning/{thread_id}")
async def get_chat_reasoning(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    runs = await RunStore(db).list_for_thread(
        thread_scope.internal_id,
        user_id=user.id,
    )
    if not runs:
        raise HTTPException(status_code=404, detail="Thread not found")
    events = await EventStore(db).list_for_runs([runs[-1].run_id])
    reasoning = "".join(
        str(event.payload.get("content", ""))
        for event in events
        if event.event_type == "thinking_chunk"
        and isinstance(event.payload.get("content", ""), str)
    )
    return {"thread_id": thread_id, "reasoning_trace": reasoning}


@router.delete("/chat/history/{thread_id}")
async def delete_chat_history(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    thread_scope = _resolve_user_thread(user, thread_id)
    deleted_runs = await RunStore(db).delete_thread(
        thread_scope.internal_id,
        user_id=user.id,
    )
    return {
        "status": "deleted",
        "thread_id": thread_id,
        "deleted_runs": deleted_runs,
    }


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

    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    if not isinstance(run_id, str) or not run_id.strip():
        raise HTTPException(status_code=400, detail="run_id is required")
    run = await RunStore(db).get(run_id, user_id=user.id)
    if run is None or run.thread_id != thread_scope.internal_id:
        raise HTTPException(status_code=404, detail="Run not found")
    run = await _recover_stale_run(run, db)
    if run.status not in {"running", "paused"}:
        raise HTTPException(status_code=409, detail="Run is not resumable")
    if not _checkpoint_adapter_enabled():
        raise HTTPException(
            status_code=409,
            detail="Checkpoint recovery is not configured for this Run",
        )

    checkpoint_store = SqliteCheckpointStore(settings.CHECKPOINT_DB_PATH)
    state = await checkpoint_store.load(run_id, thread_scope.internal_id)
    if state is None:
        await checkpoint_store.close()
        raise HTTPException(status_code=409, detail="Run checkpoint is not resumable")
    pending = state.context.get("pending_decision")
    if not isinstance(pending, dict):
        await checkpoint_store.close()
        raise HTTPException(status_code=409, detail="Run has no pending approval")

    capability_registry = build_capability_registry()
    capability_name = pending.get("capability")
    owner = capability_registry.find_action(str(capability_name or ""))
    if owner is None or not owner[1].approval_required:
        await checkpoint_store.close()
        raise HTTPException(status_code=409, detail="Run approval target is no longer configured")

    approval = Approval(
        approval_id=f"approval:{run_id}:{pending.get('decision_id', 'pending')}",
        approved=decision == "approve",
        principal_id=user.id,
        action=owner[1].name,
    )
    api_key = x_api_key or os.getenv("OPENAI_API_KEY")
    base_url = _resolve_provider_base_url(x_base_url)
    if not api_key and not (
        settings.DEPLOY_MODE == "local" and is_local_endpoint(base_url)
    ):
        await checkpoint_store.close()
        raise HTTPException(status_code=401, detail="Missing API Key")

    task = state.task.model_copy(deep=True)
    task.metadata["run_id"] = run_id
    task.metadata["thread_id"] = thread_scope.internal_id
    task.metadata.setdefault("model", run.model)
    trace_id = str(state.context.get("trace_id") or run_id)
    execution_context = ExecutionContext(
        principal_id=user.id,
        run_id=run_id,
        trace_id=trace_id,
        capability_allowlist=frozenset(
            definition.public_name
            for definition in capability_registry.allowed_public_definitions(
                include_side_effects=True
            )
        ),
        thread_id=thread_scope.internal_id,
    )
    cancellation = CancellationToken()
    cancellation_store.register(run_id, cancellation)

    async def stream_generator():
        model_gateway: Optional[OpenAIModelGateway] = None
        try:
            model_gateway = OpenAIModelGateway(
                api_key=api_key,
                base_url=base_url,
                model=str(task.metadata.get("model") or run.model),
                temperature=0.6,
                endpoint_policy=_provider_endpoint_policy(),
            )
            policy_engine = PolicyEngine(allow_side_effects=True)
            idempotency_store = SqlIdempotencyStore(db)
            dispatcher = Dispatcher(
                capability_registry,
                policy_engine=policy_engine,
                approval=approval,
                idempotency_store=idempotency_store,
                adapter_factory=_capability_adapter_factory(
                    db=db,
                    user=user,
                    policy_engine=policy_engine,
                    approval=approval,
                    idempotency_store=idempotency_store,
                ),
            )
            runtime = AgentRuntime(
                checkpoint_store=checkpoint_store,
                trace_store=SqlTraceStore(db),
                model_gateway=model_gateway,
                dispatcher=dispatcher,
                run_store=RunStore(db),
                event_store=EventStore(db),
                checkpoint_lease_seconds=settings.CHECKPOINT_LEASE_SECONDS,
            )
            async for chunk_data in runtime.stream_decision(
                task,
                context=execution_context,
                cancellation=cancellation,
                approval=approval,
            ):
                event_type = chunk_data.get("type", "message")
                diagnostic_data = _chat_sse_projection(
                    chunk_data,
                    durable=True,
                )
                diagnostic_data["thread_id"] = thread_scope.public_id
                diagnostic_data["run_id"] = run_id
                yield format_sse(
                    event=event_type,
                    data=diagnostic_data,
                    event_id=chunk_data.get("sequence"),
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
            await checkpoint_store.close()
            if model_gateway is not None:
                await model_gateway.close()

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/chat/threads")
async def list_chat_threads(
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    internal_ids = await RunStore(db).list_threads(user_id=user.id)
    thread_ids = [
        public_id
        for internal_id in internal_ids
        if (public_id := public_thread_id(user.id, internal_id)) is not None
    ]
    return {"threads": thread_ids}


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
