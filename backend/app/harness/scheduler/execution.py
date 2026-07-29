"""Scheduled-task adapter and execution policy."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.harness.policy import ProactivePolicy
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask


def build_agent_task(task_def: Any, run: Any) -> AgentTask:
    goal = (
        "推荐动漫"
        if task_def.task_type in {"weekly_recommendation", "seasonal_scan"}
        else f"execute {task_def.task_type}"
    )
    return AgentTask(
        task_id=getattr(run, "id", None),
        user_id=task_def.user_id,
        goal=goal,
        metadata={
            "task_def_id": task_def.id,
            "run_id": run.id,
            "task_type": task_def.task_type,
            "payload": task_def.payload,
            "idempotency_key": getattr(task_def, "idempotency_key", None)
            or f"{task_def.id}:{run.scheduled_slot.isoformat()}",
            "scheduled_slot": run.scheduled_slot.isoformat(),
            "trace_id": f"scheduled:{task_def.id}:{run.id}",
        },
    )


class _SpecialistAdapter:
    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def run(self, state: Any) -> Any:
        return await self.agent.execute(state.task)


async def handle_task_def(
    task_def: Any,
    run: Any,
    runtime: Any,
    router: Any,
    *,
    repository: Any = None,
) -> Any:
    if not task_def.enabled:
        return None
    lease_id = run.lease_id
    try:
        policy = ProactivePolicy.from_json(getattr(task_def, "policy", "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        run.status = "failed"
        run.error_category = "invalid_policy"
        if repository is not None:
            await repository.finish(
                run, success=False, error_category="invalid_policy", lease_id=lease_id
            )
        raise
    agent_task = build_agent_task(task_def, run)
    agent_task.metadata["policy"] = json.loads(getattr(task_def, "policy", "{}") or "{}")
    run.trace_id = agent_task.metadata["trace_id"]
    decision = router.route(agent_task.goal) if router is not None else None
    agent = router.select(decision) if decision is not None else None
    selected_runtime = runtime
    if agent is not None:
        if policy.extra.get("requires_side_effect") and not policy.allows("agent.execute"):
            run.status = "failed"
            run.error_category = "policy_denied"
            if repository is not None:
                await repository.finish(run, success=False, error_category="policy_denied", lease_id=lease_id)
            raise PermissionError("scheduled policy does not allow side effects")
        selected_runtime = AgentRuntime(
            _SpecialistAdapter(agent), trace_store=getattr(runtime, "trace_store", None)
        )

    for attempt in range(policy.max_retries + 1):
        try:
            state = await asyncio.wait_for(
                selected_runtime.execute(agent_task), timeout=policy.timeout_seconds
            )
        except asyncio.CancelledError:
            run.status = "cancelled"
            run.error_category = "cancelled"
            if repository is not None:
                await repository.finish(run, success=False, error_category="cancelled", lease_id=lease_id)
            raise
        except asyncio.TimeoutError:
            category = "timeout"
            run.error_category = category
            run.status = "failed"
            if repository is not None:
                await repository.finish(run, success=False, error_category=category, lease_id=lease_id)
            raise
        except Exception as exc:
            category = getattr(exc, "error_category", "permanent")
            if category == "transient" and attempt < policy.max_retries:
                await asyncio.sleep(min(2**attempt, 30))
                continue
            run.error_category = category
            run.status = "failed"
            if repository is not None:
                await repository.finish(run, success=False, error_category=category, lease_id=lease_id)
            raise
        else:
            result = getattr(state, "result", None)
            if isinstance(result, dict) and result.get("evidence", {}).get("reason") == "policy_denied":
                run.status = "failed"
                run.error_category = "policy_denied"
                if repository is not None:
                    await repository.finish(
                        run, success=False, error_category="policy_denied", lease_id=lease_id
                    )
                raise PermissionError("scheduled policy denied capability")
            run.status = "success"
            if repository is not None:
                await repository.finish(run, success=True, lease_id=lease_id)
            return state

    raise RuntimeError("scheduled execution exhausted retries")
