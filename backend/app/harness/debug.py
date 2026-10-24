"""Python ingress for a new, durable Run driven by the real Decision Runtime.

Callers supply an authenticated ExecutionContext and a dedicated Runtime/session.
This is an internal backend API, not an authentication mechanism or HTTP route.
The caller owns dependency cleanup. Do not share a Runtime/session concurrently;
resume and replay use their existing Runtime entrypoints.
"""

from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import (
    ContractModel,
    ExecutionContext,
    RunEvent,
    RunRequest,
    termination_reason_for,
)
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


class DebugRunReport(ContractModel):
    """A versioned snapshot of durable facts, without raw provider responses."""

    run_id: str
    principal_id: int
    status: str
    error_code: str | None = None
    termination_reason: str | None = None
    events: list[RunEvent]


async def run_debug(
    request: RunRequest,
    context: ExecutionContext,
    *,
    runtime: AgentRuntime,
    budget: RunBudget | None = None,
    cancellation: CancellationToken | None = None,
) -> DebugRunReport:
    """Validate ingress, drain Runtime, then read the authoritative Run facts.

    Identity comes only from the trusted context, never from model messages.
    Any existing Run ID is rejected; callers must allocate a fresh Run ID and
    dedicated dependencies for each invocation. Runtime retains sole ownership
    of Decision parsing, dispatch, lifecycle transitions and persistence.
    """
    request = RunRequest.model_validate(request.model_dump()).model_copy(deep=True)
    context = ExecutionContext.model_validate(context.model_dump()).model_copy(
        deep=True
    )
    principal_id = context.principal_id
    if principal_id is None or principal_id <= 0:
        raise ValueError("debug Run requires an authenticated principal")
    if not request.run_id.strip() or request.run_id != context.run_id:
        raise ValueError("debug Run identity does not match trusted context")
    if request.user_id is not None and request.user_id != principal_id:
        raise ValueError("debug Run principal does not match trusted context")

    run_store, event_store = runtime.run_store, runtime.event_store
    if (
        run_store is None
        or event_store is None
        or runtime.model_gateway is None
        or runtime.dispatcher is None
    ):
        raise ValueError("debug Run requires configured Runtime and durable stores")
    if await run_store.get(request.run_id) is not None:
        raise ValueError("debug Run ID already exists")

    task = AgentTask(
        user_id=principal_id,
        goal=request.goal,
        task_metadata={
            "run_id": context.run_id,
            "trace_id": context.trace_id,
            "thread_id": context.thread_id,
            "model": request.model,
            "messages": request.messages,
        },
    )
    async for _ in runtime.stream_decision(
        task, context=context, budget=budget, cancellation=cancellation
    ):
        pass

    stored = await run_store.get(request.run_id, user_id=principal_id)
    if stored is None or stored.status in {"queued", "running"}:
        raise RuntimeError("Runtime did not persist a paused or terminal Run")

    events: list[RunEvent] = []
    after_sequence = 0
    while page := await event_store.list_after(
        request.run_id, after_sequence=after_sequence, limit=1000
    ):
        events.extend(
            RunEvent(
                run_id=item.run_id,
                sequence=item.sequence,
                event_type=item.event_type,
                invocation_id=item.invocation_id,
                payload=item.payload,
            )
            for item in page
        )
        after_sequence = page[-1].sequence
    reason = next(
        (
            item.payload["termination_reason"]
            for item in reversed(events)
            if item.event_type
            in {"run.succeeded", "run.failed", "run.cancelled", "run.abandoned"}
            and isinstance(item.payload.get("termination_reason"), str)
            and item.payload["termination_reason"].strip()
        ),
        None,
    )
    if reason is None and stored.status != "paused":
        reason = termination_reason_for(stored.status, stored.error_code)
    return DebugRunReport(
        run_id=stored.run_id,
        principal_id=principal_id,
        status=stored.status,
        error_code=stored.error_code,
        termination_reason=reason,
        events=events,
    )
