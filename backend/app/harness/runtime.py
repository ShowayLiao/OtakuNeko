from __future__ import annotations

import asyncio
import os
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol

from app.harness.checkpoint import CheckpointStore
from app.harness.budget import CancellationToken, RunBudget
from app.harness.coordinator import RunCoordinator
from app.harness.contracts import RunResult
from app.harness.model_gateway import ModelGateway
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import RunStore
from app.harness.result import AgentResult
from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.trace import AgentTrace, TraceEvent, TraceEventType, TraceStep
from app.trace.redaction import sanitize_trace
from app.trace.recorder import bind_trace
from app.trace.store import TraceStore
from app.core.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentAdapter(Protocol):
    """Protocol for agent implementations that the runtime can invoke.

    Non-streaming agents implement this protocol.
    """

    async def run(self, state: AgentState) -> Any:
        ...


class StreamingAgentAdapter(Protocol):
    """Protocol for agents that expose incremental output."""

    async def stream(self, state: AgentState, **kwargs: Any) -> AsyncIterator[Any]:
        ...


class AgentRuntime:
    """Execution wrapper around an agent adapter.

    Responsibilities:
    - receive task
    - create state
    - invoke adapter
    - return result

    When a TraceStore is provided, the runtime emits lifecycle trace
    events (task_start, task_end, task_failed) automatically.  No
    overhead when trace_store is None (the default).
    """

    def __init__(
        self,
        adapter: AgentAdapter | StreamingAgentAdapter,
        checkpoint_store: CheckpointStore | None = None,
        *,
        trace_store: TraceStore | None = None,
        model_gateway: ModelGateway | None = None,
        max_model_calls: int = 1,
        run_store: RunStore | None = None,
        event_store: EventStore | None = None,
    ):
        self.adapter = adapter
        self.checkpoint_store = checkpoint_store
        self.trace_store = trace_store
        self.model_gateway = model_gateway
        self.max_model_calls = max_model_calls
        self.run_store = run_store
        self.event_store = event_store

    @property
    def adapter_name(self) -> str:
        """Human-readable identifier for the wrapped adapter."""
        cls = getattr(self.adapter, "__class__", None)
        if cls is not None:
            return cls.__name__
        return type(self.adapter).__name__

    async def _save_checkpoint(self, state: AgentState) -> None:
        if self.checkpoint_store is not None:
            await self.checkpoint_store.save_state(state)

    async def _record_trace(self, trace: AgentTrace) -> None:
        if self.trace_store is None:
            return
        try:
            await self.trace_store.record(sanitize_trace(trace))
        except Exception:
            logger.exception(
                "trace_storage_failed",
                extra={"trace_id": trace.trace_id},
            )

    async def execute(self, task: AgentTask) -> AgentState:
        trace: AgentTrace | None = None
        if self.trace_store is not None:
            trace = AgentTrace(
                task_id=task.task_id,
                user_id=task.user_id,
                agent_name=self.adapter_name,
                goal=task.goal,
            )
            if task.metadata.get("trace_id"):
                trace.trace_id = str(task.metadata["trace_id"])
            scheduled_step = TraceStep(
                    step_index=0,
                    step_label="scheduled_context",
                    agent_name=self.adapter_name,
                    input_summary=str(
                        {
                            "task_def_id": task.metadata.get("task_def_id"),
                            "run_id": task.metadata.get("run_id"),
                            "scheduled_slot": task.metadata.get("scheduled_slot"),
                        }
                    ),
                )
            scheduled_step.complete()
            trace.steps.append(scheduled_step)

        state = AgentState(task=task, status="running")
        await self._save_checkpoint(state)
        try:
            trace_context = bind_trace(trace) if trace is not None else nullcontext()
            with trace_context as recorder:
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_START,
                        "agent.execute",
                        {"agent": self.adapter_name},
                    )
                try:
                    state.result = await self.adapter.run(state)
                except BaseException as exc:
                    if recorder is not None:
                        status = (
                            "cancelled"
                            if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                            else "failed"
                        )
                        recorder.record(
                            TraceEventType.FAILURE,
                            "agent.execute",
                            {"error_category": type(exc).__name__},
                            status=status,
                        )
                        recorder.record(
                            TraceEventType.NODE_END,
                            "agent.execute",
                            {"outcome": status},
                            status=status,
                        )
                    raise
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_END,
                        "agent.execute",
                        {"outcome": "completed"},
                    )
            state.status = "completed"
            if trace is not None:
                trace.mark_completed()
        except (asyncio.CancelledError, GeneratorExit):
            state.status = "cancelled"
            if trace is not None:
                trace.mark_cancelled()
            await self._save_checkpoint(state)
            raise
        except Exception:
            state.status = "failed"
            if trace is not None:
                trace.mark_failed("execute() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                await self._record_trace(trace)
        await self._save_checkpoint(state)
        return state

    async def stream(self, task: AgentTask, **kwargs: Any) -> AsyncIterator[Any]:
        """Stream through the single Run Coordinator while preserving chunks."""
        enabled = os.getenv("HARNESS_COORDINATOR_ENABLED", "true").lower()
        if enabled in {"0", "false", "off", "no"}:
            async for chunk in self._legacy_stream(task, **kwargs):
                yield chunk
            return

        trace: AgentTrace | None = None
        if self.trace_store is not None:
            trace = AgentTrace(
                task_id=task.task_id,
                user_id=task.user_id,
                agent_name=self.adapter_name,
                goal=task.goal,
            )

        stream_kwargs = dict(kwargs)
        supplied_budget = stream_kwargs.pop("budget", None)
        supplied_cancellation = stream_kwargs.pop("cancellation", None)
        budget = supplied_budget or self._build_run_budget(task, stream_kwargs)
        if not isinstance(budget, RunBudget):
            raise TypeError("budget must be a RunBudget")
        cancellation = supplied_cancellation or CancellationToken()
        if not isinstance(cancellation, CancellationToken):
            raise TypeError("cancellation must be a CancellationToken")

        state = AgentState(task=task, status="running", context=stream_kwargs)
        state.context["orchestrate_results"] = self.model_gateway is not None
        await self._save_checkpoint(state)
        stream_completed = False
        terminal: RunResult | None = None
        coordinator = RunCoordinator(
            self.adapter,
            model_gateway=self.model_gateway,
            max_model_calls=self.max_model_calls,
            fallback_from_result=self._fallback_from_result,
            run_store=(
                self.run_store
                if os.getenv("INTERACTIVE_RUN_STORE_ENABLED", "true").lower()
                not in {"0", "false", "off", "no"}
                else None
            ),
            event_store=(
                self.event_store
                if os.getenv("INTERACTIVE_RUN_STORE_ENABLED", "true").lower()
                not in {"0", "false", "off", "no"}
                else None
            ),
        )
        try:
            trace_context = bind_trace(trace) if trace is not None else nullcontext()
            with trace_context as recorder:
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_START,
                        "agent.stream",
                        {"agent": self.adapter_name},
                    )
                try:
                    async for item in coordinator.stream(
                        task,
                        state.context,
                        budget=budget,
                        cancellation=cancellation,
                        state=state,
                    ):
                        if isinstance(item, RunResult):
                            terminal = item
                            continue
                        if trace is not None and isinstance(item, dict):
                            self._record_stream_trace(trace, item)
                        yield item

                    terminal = terminal or coordinator.terminal_result
                    if terminal is None:
                        raise RuntimeError("Coordinator ended without a terminal result")
                    if coordinator.failure is not None:
                        raise coordinator.failure
                    if terminal.status == "completed":
                        stream_completed = True
                    if recorder is not None:
                        if terminal.status in {"failed", "timeout"}:
                            recorder.record(
                                TraceEventType.FAILURE,
                                "agent.stream",
                                {
                                    "error_code": terminal.error_code.value
                                    if terminal.error_code
                                    else "failed"
                                },
                                status=(
                                    "timeout"
                                    if terminal.status == "timeout"
                                    else "failed"
                                ),
                            )
                        recorder.record(
                            TraceEventType.NODE_END,
                            "agent.stream",
                            {"outcome": terminal.status},
                            status=(
                                terminal.status
                                if terminal.status in {"cancelled", "timeout"}
                                else (
                                    "failed"
                                    if terminal.status == "failed"
                                    else "completed"
                                )
                            ),
                        )
                except BaseException as exc:
                    if recorder is not None:
                        status = (
                            "cancelled"
                            if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                            else "failed"
                        )
                        recorder.record(
                            TraceEventType.FAILURE,
                            "agent.stream",
                            {"error_category": type(exc).__name__},
                            status=status,
                        )
                        recorder.record(
                            TraceEventType.NODE_END,
                            "agent.stream",
                            {"outcome": status},
                            status=status,
                        )
                    raise
            if terminal is not None:
                state.terminal_result = terminal
                state.status = terminal.status
                state.result = terminal.content
                state.budget = budget.snapshot()
                if trace is not None:
                    if terminal.status == "completed":
                        trace.mark_completed()
                    elif terminal.status == "cancelled":
                        trace.mark_cancelled()
                    else:
                        trace.mark_failed(terminal.error_code.value if terminal.error_code else terminal.status)
        except (asyncio.CancelledError, GeneratorExit):
            state.status = "cancelled"
            state.terminal_result = coordinator.terminal_result
            state.budget = budget.snapshot()
            if trace is not None:
                trace.mark_cancelled()
            await self._save_checkpoint(state)
            raise
        except Exception:
            state.status = "failed"
            state.terminal_result = coordinator.terminal_result
            state.budget = budget.snapshot()
            if trace is not None:
                trace.mark_failed("stream() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                if trace.status == "running":
                    if stream_completed:
                        trace.mark_completed()
                    else:
                        trace.mark_cancelled()
                await self._record_trace(trace)
        await self._save_checkpoint(state)

    def _build_run_budget(
        self, task: AgentTask, context: dict[str, Any]
    ) -> RunBudget:
        policy = task.metadata.get("policy") or {}
        defaults = RunBudget()
        values: dict[str, Any] = {}
        for field in (
            "max_steps",
            "max_tool_calls",
            "max_model_calls",
            "deadline_seconds",
            "max_total_tokens",
            "max_cost_usd",
        ):
            if field in context:
                values[field] = context[field]
            elif field in policy:
                values[field] = policy[field]
            else:
                values[field] = getattr(defaults, field)
        return RunBudget(**values)

    async def _legacy_stream(self, task: AgentTask, **kwargs: Any) -> AsyncIterator[Any]:
        """Pre-BATCH-05 facade retained for the explicit rollback flag."""
        trace: AgentTrace | None = None
        if self.trace_store is not None:
            trace = AgentTrace(
                task_id=task.task_id,
                user_id=task.user_id,
                agent_name=self.adapter_name,
                goal=task.goal,
            )

        state = AgentState(task=task, status="running", context=kwargs)
        state.context["orchestrate_results"] = self.model_gateway is not None
        await self._save_checkpoint(state)
        stream_completed = False
        try:
            stream = getattr(self.adapter, "stream", None)
            if stream is None:
                raise TypeError("The configured adapter does not support streaming")
            trace_context = bind_trace(trace) if trace is not None else nullcontext()
            with trace_context as recorder:
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_START,
                        "agent.stream",
                        {"agent": self.adapter_name},
                    )
                try:
                    model_calls_used = 0
                    execution_results: list[AgentResult] = []
                    async for chunk in stream(state, **kwargs):
                        if trace is not None and isinstance(chunk, dict):
                            self._record_stream_trace(trace, chunk)
                        if (
                            isinstance(chunk, dict)
                            and chunk.get("type") == "agent_result"
                        ):
                            result = AgentResult.from_raw(
                                chunk.get("result", {}),
                                kind=chunk.get("kind", "subagent"),
                                name=str(chunk.get("agent", "unknown")),
                            )
                            execution_results.append(result)
                            normalized_chunk = {
                                **chunk,
                                "kind": result.kind,
                                "agent": result.name,
                                "result": result.model_dump(),
                            }
                            yield normalized_chunk

                            if self.model_gateway is None:
                                continue

                            budget = int(
                                kwargs.get(
                                    "max_model_calls",
                                    (task.metadata.get("policy") or {}).get(
                                        "max_model_calls", self.max_model_calls
                                    ),
                                )
                            )
                            if model_calls_used >= budget:
                                content = self._fallback_from_result(
                                    result, "model_budget_exhausted"
                                )
                                synthesis_status = "degraded"
                            else:
                                try:
                                    model_calls_used += 1
                                    content = await self.model_gateway.synthesize(
                                        goal=task.goal,
                                        messages=kwargs.get("messages")
                                        or task.metadata.get("messages", []),
                                        results=execution_results,
                                        model_calls_used=model_calls_used,
                                    )
                                    content = content or self._fallback_from_result(
                                        result, "empty_model_response"
                                    )
                                    synthesis_status = "completed"
                                except Exception:
                                    logger.warning(
                                        "model_synthesis_failed", exc_info=True
                                    )
                                    content = self._fallback_from_result(
                                        result, "model_synthesis_failed"
                                    )
                                    synthesis_status = "degraded"

                            yield {"type": "message_start"}
                            yield {"type": "message_chunk", "content": content}
                            yield {"type": "message_end"}
                            yield {
                                "type": "agent_complete",
                                "agent": result.name,
                                "kind": result.kind,
                                "status": synthesis_status,
                                "candidates": result.data.get("candidates", []),
                                "evidence": {
                                    **result.evidence,
                                    "model_calls_used": model_calls_used,
                                    "synthesis_status": synthesis_status,
                                },
                            }
                            continue
                        yield chunk
                except BaseException as exc:
                    if recorder is not None:
                        status = (
                            "cancelled"
                            if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                            else "failed"
                        )
                        recorder.record(
                            TraceEventType.FAILURE,
                            "agent.stream",
                            {"error_category": type(exc).__name__},
                            status=status,
                        )
                        recorder.record(
                            TraceEventType.NODE_END,
                            "agent.stream",
                            {"outcome": status},
                            status=status,
                        )
                    raise
                if recorder is not None:
                    recorder.record(
                        TraceEventType.NODE_END,
                        "agent.stream",
                        {"outcome": "completed"},
                    )
            stream_completed = True
        except (asyncio.CancelledError, GeneratorExit):
            state.status = "cancelled"
            if trace is not None:
                trace.mark_cancelled()
            await self._save_checkpoint(state)
            raise
        except Exception:
            state.status = "failed"
            if trace is not None:
                trace.mark_failed("stream() raised an exception")
            await self._save_checkpoint(state)
            raise
        finally:
            if trace is not None and self.trace_store is not None:
                if trace.status == "running":
                    if stream_completed:
                        trace.mark_completed()
                    else:
                        trace.mark_cancelled()
                await self._record_trace(trace)
        state.status = "completed"
        await self._save_checkpoint(state)

    def _record_stream_trace(self, trace: AgentTrace, chunk: dict[str, Any]) -> None:
        if chunk.get("type") == "agent_result":
            result = chunk.get("result") or {}
            data = result.get("data") if isinstance(result, dict) else {}
            step = TraceStep(
                step_index=len(trace.steps),
                step_label="agent.result",
                agent_name=str(chunk.get("agent", self.adapter_name)),
                output_summary=str(result.get("status", "completed"))
                if isinstance(result, dict)
                else "completed",
            )
            step.events.append(
                TraceEvent(
                    event_type=TraceEventType.AGENT_RESULT,
                    correlation_id=trace.trace_id,
                    data={
                        "kind": chunk.get("kind", "subagent"),
                        "name": chunk.get("agent", "unknown"),
                        "status": result.get("status", "completed")
                        if isinstance(result, dict)
                        else "completed",
                        "data_keys": sorted(data.keys())
                        if isinstance(data, dict)
                        else [],
                    },
                    status="completed",
                )
            )
            step.complete()
            trace.add_step(step)
            return
        if chunk.get("type") != "route_decision":
            return
        step = TraceStep(
            step_index=len(trace.steps),
            step_label="routing",
            agent_name=str(chunk.get("agent", self.adapter_name)),
            output_summary=str(chunk.get("route", "unknown")),
        )
        step.events.append(
            TraceEvent(
                event_type=TraceEventType.ROUTING_DECISION,
                correlation_id=trace.trace_id,
                data={
                    "route": chunk.get("route"),
                    "agent": chunk.get("agent"),
                    "confidence": chunk.get("confidence"),
                    "rationale_present": bool(chunk.get("rationale")),
                },
                status="completed",
            )
        )
        step.complete()
        trace.add_step(step)

    @staticmethod
    def _fallback_from_result(result: AgentResult, reason: str) -> str:
        """Return a safe deterministic answer when synthesis is unavailable."""
        if reason == "model_budget_exhausted":
            prefix = "模型调用预算不足，已完成工具检索。"
        else:
            prefix = "已完成信息检索，暂时无法生成详细整合报告。"
        candidates = result.data.get("candidates", [])
        if candidates:
            names = []
            for candidate in candidates[:5]:
                if isinstance(candidate, dict):
                    name = candidate.get("name") or candidate.get("label")
                    if name:
                        names.append(str(name))
            if names:
                return prefix + "候选内容：\n" + "\n".join(
                    f"{index}. {name}" for index, name in enumerate(names, 1)
                )
        if reason == "model_budget_exhausted":
            return prefix + "暂时无法生成整合回答。"
        return "已完成工具检索，但暂时无法生成详细整合回答，请稍后重试。"
