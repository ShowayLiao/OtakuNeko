"""Single in-memory Run Coordinator for interactive agent streams."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from app.harness.budget import (
    BudgetExceededError,
    CancellationToken,
    DeadlineExceededError,
    RunCancellationError,
    RunBudget,
)
from app.harness.contracts import ErrorCode, RunEvent, RunResult
from app.harness.model_gateway import ModelGateway
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.run_store import InvalidRunTransition, RunStore
from app.harness.result import AgentResult
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.models.agent_run import AgentRun


_STEP_EVENTS = {
    "route_decision",
    "thinking_start",
    "message_start",
    "tool_call_start",
    "agent_result",
    "error",
}
_MODEL_EVENTS = {"thinking_start", "message_start", "model_call"}
_COORDINATOR_ONLY_CONTEXT = {
    "orchestrate_results",
    "synthesis_model_calls_used",
    "budget",
    "cancellation",
    "max_steps",
    "max_tool_calls",
    "max_model_calls",
    "deadline_seconds",
    "max_total_tokens",
    "max_cost_usd",
}

_PERSISTED_STREAM_EVENTS = {
    "thinking_start",
    "thinking_end",
    "tool_call_start",
    "tool_call_end",
    "message_input",
    "message_start",
    "message_chunk",
    "message_end",
    "model_decision",
    "tool_requested",
    "error",
}


def _adapt_stream_event(
    event: dict[str, Any],
    *,
    run_id: str,
    sequence: int,
) -> RunEvent | None:
    """Project a provider-neutral stream event into a safe Run fact."""
    event_type = event.get("type")
    if event_type not in _PERSISTED_STREAM_EVENTS:
        return None

    invocation_id = event.get("invocation_id", event.get("id"))
    payload: dict[str, Any] = {}
    if event_type == "tool_call_start":
        inputs = event.get("inputs", event.get("arguments"))
        payload = {
            "name": str(event.get("name") or event.get("capability") or "unknown"),
            "argument_keys": sorted(
                event.get("argument_keys", inputs.keys() if isinstance(inputs, dict) else [])
            ),
        }
    elif event_type == "tool_call_end":
        payload = {
            "name": str(event.get("name") or event.get("capability") or "unknown"),
            "status": str(event.get("status", "unknown")),
        }
        if isinstance(event.get("duration_ms"), (int, float)):
            payload["duration_ms"] = event["duration_ms"]
    elif event_type == "message_input":
        payload = {
            "role": "user",
            "content": str(event.get("content", "")),
        }
    elif event_type == "message_chunk":
        payload = {"content": str(event.get("content", ""))}
    elif event_type == "error":
        payload = {"error_code": str(event.get("error_code", "permanent"))}
    elif event_type == "model_decision":
        decision = event.get("decision")
        payload = {
            "action": (
                decision.get("action")
                if isinstance(decision, dict)
                else event.get("action", "unknown")
            ),
            "capability": (
                decision.get("capability")
                if isinstance(decision, dict)
                else event.get("capability")
            ),
            "capability_version": (
                decision.get("capability_version")
                if isinstance(decision, dict)
                else event.get("capability_version")
            ),
            "argument_keys": sorted(event.get("argument_keys", [])),
        }
    elif event_type == "tool_requested":
        payload = {
            "name": str(event.get("name", "unknown")),
            "capability": str(event.get("capability", "unknown")),
        }

    return RunEvent(
        run_id=run_id,
        sequence=sequence,
        event_type=str(event_type),
        invocation_id=str(invocation_id) if invocation_id is not None else None,
        payload=payload,
    )


class PersistenceHalt(RuntimeError):
    """Persistence failed; the Run must not be reported as successful."""


class RunCoordinator:
    """Own the terminal state of one interactive Run.

    The wrapped adapter remains responsible for its internal loop and legacy
    chunks. The Coordinator is the only component that decides whether the
    outer Run completed, failed, timed out or was cancelled. It yields legacy
    chunks for compatibility and exactly one versioned ``RunResult`` at the
    end; converted ``RunEvent`` objects remain available as internal facts.
    """

    def __init__(
        self,
        adapter: Any,
        *,
        model_gateway: ModelGateway | None = None,
        max_model_calls: int = 1,
        fallback_from_result: Callable[[AgentResult, str], str] | None = None,
        run_store: RunStore | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        if (run_store is None) != (event_store is None):
            raise ValueError("run_store and event_store must be configured together")
        self.adapter = adapter
        self.model_gateway = model_gateway
        self.max_model_calls = max_model_calls
        self._fallback_from_result = fallback_from_result
        self.run_store = run_store
        self.event_store = event_store
        self.events: list[RunEvent] = []
        self.terminal_result: RunResult | None = None
        self.failure: BaseException | None = None
        self.budget: RunBudget | None = None
        self.cancellation: CancellationToken | None = None
        self._pending_chunks: list[dict[str, Any]] = []
        self._persist_sequence = 0
        self._terminal_persisted = False
        self.persistence_failure: BaseException | None = None
        self._active_invocations: dict[str, list[str]] = {}
        self._existing_run_status: str | None = None

    async def stream(
        self,
        task: AgentTask,
        context: dict[str, Any] | None = None,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[dict[str, Any] | RunResult]:
        """Run one adapter stream and yield legacy chunks plus one terminal result."""
        self.events = []
        self.terminal_result = None
        self.failure = None
        self.persistence_failure = None
        self._persist_sequence = 0
        self._terminal_persisted = False
        self._active_invocations = {}
        self._existing_run_status = None
        self.budget = budget or RunBudget()
        self.cancellation = cancellation or CancellationToken()
        run_id = str((task.metadata or {}).get("run_id") or task.task_id or uuid4().hex)
        self._run_id = run_id
        self._pending_chunks = []
        execution_state = state or AgentState(
            task=task,
            status="running",
            context=dict(context or {}),
        )
        run_context = dict(context or execution_state.context)
        adapter_context = {
            key: value
            for key, value in run_context.items()
            if key not in _COORDINATOR_ONLY_CONTEXT
        }
        execution_state.context.update(adapter_context)
        execution_results: list[AgentResult] = []
        message_parts: list[str] = []
        iterator: Any = None

        try:
            await self._persist_run_start(task, run_context, run_id)
            self.cancellation.raise_if_cancelled()
            self.budget.check_deadline()
            adapter_stream = getattr(self.adapter, "stream", None)
            if adapter_stream is None:
                raise TypeError("The configured adapter does not support streaming")
            iterator = adapter_stream(execution_state, **adapter_context).__aiter__()

            while self.terminal_result is None:
                self.cancellation.raise_if_cancelled()
                self.budget.check_deadline()
                next_task = asyncio.create_task(iterator.__anext__())
                cancellation_task = asyncio.create_task(self.cancellation.wait())
                try:
                    done, _ = await asyncio.wait(
                        {next_task, cancellation_task},
                        timeout=self.budget.remaining_seconds(),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        raise DeadlineExceededError("run deadline exceeded")
                    if cancellation_task in done:
                        raise RunCancellationError()
                    chunk = next_task.result()
                except StopAsyncIteration:
                    break
                finally:
                    if not next_task.done():
                        next_task.cancel()
                    if not cancellation_task.done():
                        cancellation_task.cancel()
                    for pending in (next_task, cancellation_task):
                        with suppress(asyncio.CancelledError, Exception):
                            await pending

                if not isinstance(chunk, dict):
                    chunk = {"type": "message_chunk", "content": str(chunk)}
                event = self._record_event(chunk, run_id)
                if event is not None:
                    self._account_event(event)
                    await self._persist_event(event)

                chunk_type = str(chunk.get("type", ""))
                if chunk_type == "message_chunk":
                    message_parts.append(str(chunk.get("content", "")))
                elif chunk_type == "agent_result":
                    normalized = AgentResult.from_raw(
                        chunk.get("result", {}),
                        kind=chunk.get("kind", "subagent"),
                        name=str(chunk.get("agent", "unknown")),
                    )
                    execution_results.append(normalized)
                    chunk = {
                        **chunk,
                        "kind": normalized.kind,
                        "agent": normalized.name,
                        "result": normalized.model_dump(),
                    }

                yield chunk

                if chunk_type in {
                    "error",
                    "policy_denied",
                    "transient",
                    "timeout",
                    "cancelled",
                }:
                    error_code = self._error_code(
                        chunk.get("error_code") or chunk_type
                    )
                    self._finish(
                        "timeout"
                        if error_code == ErrorCode.TIMEOUT
                        else (
                            "cancelled"
                            if error_code == ErrorCode.CANCELLED
                            else "failed"
                        ),
                        error_code,
                    )
                    break
                if chunk_type in {"run_completed", "run_failed", "run_cancelled"}:
                    self._finish_from_terminal_chunk(chunk, message_parts)
                    break
                if chunk_type == "tool_call_end":
                    status = str(chunk.get("status", "")).lower()
                    if status in {"timeout", "timed_out"}:
                        self._finish("timeout", ErrorCode.TIMEOUT)
                        break
                    if status in {"policy_denied", "denied"}:
                        self._finish("failed", ErrorCode.POLICY_DENIED)
                        break
                    if status in {"transient", "retryable"}:
                        self._finish("failed", ErrorCode.TRANSIENT)
                        break

                if chunk_type == "agent_result" and self.model_gateway is not None:
                    result = execution_results[-1]
                    await self._synthesize(
                        task,
                        run_context,
                        execution_results,
                        result,
                        message_parts,
                    )
                    pending_chunks = self._pending_chunks
                    self._pending_chunks = []
                    for generated_chunk in pending_chunks:
                        yield generated_chunk

            if self.terminal_result is None:
                self._finish("completed", None, "".join(message_parts) or None)
        except RunCancellationError:
            self._finish("cancelled", ErrorCode.CANCELLED)
        except PersistenceHalt as exc:
            self.persistence_failure = exc
            self.failure = None
            self._finish("failed", ErrorCode.PERMANENT)
        except DeadlineExceededError:
            self._finish("timeout", ErrorCode.TIMEOUT)
        except BudgetExceededError:
            self._finish("failed", ErrorCode.BUDGET_EXCEEDED)
        except asyncio.TimeoutError as exc:
            # A provider/adapter timeout is still surfaced through the legacy
            # facade; the Coordinator also records a structured timeout result.
            # A wait_for expiry at the run deadline is owned by the Coordinator
            # and is therefore not re-raised by AgentRuntime.
            if self.budget is not None and self.budget.remaining_seconds() > 0:
                self.failure = exc
            self._finish("timeout", ErrorCode.TIMEOUT)
        except asyncio.CancelledError:
            # Cancellation of the consuming asyncio task must keep propagating
            # so FastAPI/ASGI can close the request and Runtime can checkpoint it.
            self._finish("cancelled", ErrorCode.CANCELLED)
            raise
        except GeneratorExit:
            self._finish("cancelled", ErrorCode.CANCELLED)
            raise
        except Exception as exc:
            self.failure = exc
            self._finish("failed", self._exception_code(exc))
        finally:
            if iterator is not None and hasattr(iterator, "aclose"):
                with suppress(Exception):
                    await iterator.aclose()
            with suppress(Exception):
                await self._persist_terminal()

        if self.terminal_result is None:
            self._finish("completed", None)
        assert self.terminal_result is not None
        # The result is yielded exactly once, even when the adapter emitted a
        # duplicate or contradictory terminal chunk.
        yield self.terminal_result

    async def execute(
        self,
        task: AgentTask,
        context: dict[str, Any] | None = None,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        """Execute a non-streaming adapter under the same Run owner."""
        self.events = []
        self.terminal_result = None
        self.failure = None
        self.persistence_failure = None
        self._persist_sequence = 0
        self._terminal_persisted = False
        self._active_invocations = {}
        self._existing_run_status = None
        self.budget = budget or RunBudget()
        self.cancellation = cancellation or CancellationToken()
        run_id = str((task.metadata or {}).get("run_id") or task.task_id or uuid4().hex)
        self._run_id = run_id
        execution_state = state or AgentState(
            task=task,
            status="running",
            context=dict(context or {}),
        )
        execution_state.status = "running"
        if context:
            execution_state.context.update(context)

        adapter_task: asyncio.Task[Any] | None = None
        cancellation_task: asyncio.Task[None] | None = None
        try:
            await self._persist_run_start(task, execution_state.context, run_id)
            self._finish_from_existing_run()
            if self.terminal_result is not None:
                execution_state.terminal_result = self.terminal_result
                execution_state.status = self.terminal_result.status
                execution_state.budget = self.budget.snapshot()
                self._terminal_persisted = True
                return execution_state
            self.cancellation.raise_if_cancelled()
            self.budget.check_deadline()
            adapter_run = getattr(self.adapter, "run", None)
            if adapter_run is None:
                raise TypeError("The configured adapter does not support execution")
            adapter_task = asyncio.create_task(adapter_run(execution_state))
            cancellation_task = asyncio.create_task(self.cancellation.wait())
            done, _ = await asyncio.wait(
                {adapter_task, cancellation_task},
                timeout=self.budget.remaining_seconds(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                raise DeadlineExceededError("run deadline exceeded")
            if cancellation_task in done:
                raise RunCancellationError()
            execution_state.result = adapter_task.result()
            self._finish("completed", None, self._result_content(execution_state.result))
        except RunCancellationError:
            self._finish("cancelled", ErrorCode.CANCELLED)
        except DeadlineExceededError:
            self._finish("timeout", ErrorCode.TIMEOUT)
        except asyncio.TimeoutError:
            self._finish("timeout", ErrorCode.TIMEOUT)
        except asyncio.CancelledError:
            self._finish("cancelled", ErrorCode.CANCELLED)
            raise
        except Exception as exc:
            self.failure = exc
            self._finish("failed", self._exception_code(exc))
        finally:
            if adapter_task is not None and not adapter_task.done():
                adapter_task.cancel()
            if cancellation_task is not None and not cancellation_task.done():
                cancellation_task.cancel()
            for pending in (adapter_task, cancellation_task):
                if pending is not None:
                    with suppress(asyncio.CancelledError, Exception):
                        await pending
            if self.terminal_result is None:
                self._finish("failed", ErrorCode.PERMANENT)
            with suppress(Exception):
                await self._persist_terminal()

        execution_state.terminal_result = self.terminal_result
        execution_state.status = (
            self.terminal_result.status if self.terminal_result is not None else "failed"
        )
        execution_state.budget = self.budget.snapshot()
        return execution_state

    @staticmethod
    def _result_content(result: Any) -> str | None:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("content", "text", "answer"):
                value = result.get(key)
                if isinstance(value, str):
                    return value
        return None

    async def _synthesize(
        self,
        task: AgentTask,
        context: dict[str, Any],
        execution_results: list[AgentResult],
        result: AgentResult,
        message_parts: list[str],
    ) -> None:
        assert self.budget is not None
        assert self.cancellation is not None
        gateway = self.model_gateway
        assert gateway is not None
        configured_limit = context.get("max_model_calls", self.max_model_calls)
        try:
            synthesis_limit = max(0, int(configured_limit))
        except (TypeError, ValueError):
            synthesis_limit = self.max_model_calls
        synthesis_used = int(context.get("synthesis_model_calls_used", 0))
        if synthesis_used >= synthesis_limit:
            content = self._fallback(result, "model_budget_exhausted")
            status = "degraded"
        else:
            self.cancellation.raise_if_cancelled()
            self.budget.check_deadline()
            self.budget.reserve_model_call()
            try:
                content = await gateway.synthesize(
                    goal=task.goal,
                    messages=context.get("messages") or task.metadata.get("messages", []),
                    results=execution_results,
                    model_calls_used=synthesis_used + 1,
                    cancellation=self.cancellation,
                    deadline=self.budget.remaining_seconds(),
                    budget=self.budget.snapshot(),
                )
                gateway_result = getattr(gateway, "last_result", None)
                self.budget.record_model_usage(
                    getattr(gateway_result, "usage", None)
                )
                gateway_terminal = self._gateway_terminal(gateway_result)
                if gateway_terminal is not None:
                    self._finish(*gateway_terminal)
                    return
                content = content or self._fallback(result, "empty_model_response")
                status = "completed"
            except (RunCancellationError, DeadlineExceededError, BudgetExceededError):
                raise
            except asyncio.TimeoutError:
                self._finish("timeout", ErrorCode.TIMEOUT)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                gateway_result = getattr(gateway, "last_result", None)
                self.budget.record_model_usage(
                    getattr(gateway_result, "usage", None)
                )
                exception_code = self._exception_code(exc)
                if exception_code in {
                    ErrorCode.TIMEOUT,
                    ErrorCode.CANCELLED,
                    ErrorCode.POLICY_DENIED,
                    ErrorCode.TRANSIENT,
                }:
                    self._finish(
                        "timeout" if exception_code == ErrorCode.TIMEOUT else (
                            "cancelled"
                            if exception_code == ErrorCode.CANCELLED
                            else "failed"
                        ),
                        exception_code,
                    )
                    return
                content = self._fallback(result, "model_synthesis_failed")
                status = "degraded"

        context["synthesis_model_calls_used"] = synthesis_used + (
            0 if status == "degraded" and synthesis_used >= synthesis_limit else 1
        )
        message_parts.append(str(content))
        # Synthesis chunks are returned through the legacy stream. Their model
        # text is not copied into RunEvent payloads or trace decision fields.
        self._pending_chunks.extend(
            [
                {"type": "message_start"},
                {"type": "message_chunk", "content": content},
                {"type": "message_end"},
                {
                    "type": "agent_complete",
                    "agent": result.name,
                    "kind": result.kind,
                    "status": status,
                    "candidates": result.data.get("candidates", []),
                    "evidence": {
                        **result.evidence,
                        "model_calls_used": self.budget.model_calls_used,
                        "synthesis_status": status,
                    },
                },
            ]
        )

    def _record_event(self, chunk: dict[str, Any], run_id: str) -> RunEvent | None:
        sequence = len(self.events) + 1
        converted = _adapt_stream_event(chunk, run_id=run_id, sequence=sequence)
        if converted is None:
            event_type = str(chunk.get("type", "unknown"))
            payload: dict[str, Any] = {}
            if event_type in {"route_decision", "agent_result"}:
                for key in ("route", "agent", "confidence", "kind"):
                    if key in chunk:
                        payload[key] = chunk[key]
            elif event_type == "error":
                payload["error_code"] = self._error_code(chunk.get("error_code")).value
            converted = RunEvent(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                payload=payload,
            )
        elif chunk.get("type") == "error":
            converted = converted.model_copy(
                update={
                    "payload": {
                        "error_code": self._error_code(
                            chunk.get("error_code")
                        ).value
                    }
                }
            )
        self.events.append(converted)
        return converted

    def _account_event(self, event: RunEvent) -> None:
        assert self.budget is not None
        assert self.cancellation is not None
        event_type = event.event_type
        if event_type in _STEP_EVENTS:
            self.budget.consume_step()
        if event_type in {"tool_call_start", "tool_call_end"}:
            self.cancellation.raise_if_cancelled()
        if event_type == "tool_call_start":
            self.budget.consume_tool_call()
        if event_type in _MODEL_EVENTS:
            self.cancellation.raise_if_cancelled()
            self.budget.consume_model_call(None)

    def _finish(
        self,
        status: str,
        error_code: ErrorCode | None,
        content: str | None = None,
    ) -> None:
        if self.terminal_result is not None:
            return
        run_id = self._run_id
        self.terminal_result = RunResult(
            run_id=run_id,
            status=status,  # type: ignore[arg-type]
            content=content,
            error_code=error_code,
        )

    def _finish_from_terminal_chunk(
        self, chunk: dict[str, Any], message_parts: list[str]
    ) -> None:
        chunk_type = str(chunk.get("type"))
        if chunk_type == "run_completed":
            self._finish("completed", None, "".join(message_parts) or None)
        elif chunk_type == "run_cancelled":
            self._finish("cancelled", ErrorCode.CANCELLED)
        else:
            self._finish("failed", self._error_code(chunk.get("error_code")))

    @staticmethod
    def _error_code(value: Any) -> ErrorCode:
        try:
            return ErrorCode(str(value))
        except ValueError:
            return ErrorCode.PERMANENT

    @staticmethod
    def _exception_code(exc: BaseException) -> ErrorCode:
        value = getattr(exc, "error_code", None)
        try:
            return ErrorCode(str(value))
        except ValueError:
            return ErrorCode.PERMANENT

    def _fallback(self, result: AgentResult, reason: str) -> str:
        if self._fallback_from_result is not None:
            return self._fallback_from_result(result, reason)
        if reason == "model_budget_exhausted":
            return "Model call budget exhausted; tool results are available."
        return "Tool results are available, but synthesis is temporarily unavailable."

    async def _persist_run_start(
        self,
        task: AgentTask,
        context: dict[str, Any],
        run_id: str,
    ) -> None:
        if self.run_store is None or self.event_store is None:
            return
        run = await self.run_store.create(
            AgentRun(
                run_id=run_id,
                user_id=task.user_id,
                thread_id=str(task.metadata.get("thread_id"))
                if task.metadata.get("thread_id") is not None
                else None,
                status="queued",
                goal_hash=hashlib.sha256(task.goal.encode("utf-8")).hexdigest(),
                model=str(context.get("model", "")),
            )
        )
        self._existing_run_status = run.status if run.status != "queued" else None
        if run.status == "queued":
            await self.run_store.transition(run_id, "running")
            self._persist_sequence = 1
            await self.event_store.append(
                RunEvent(
                    run_id=run_id,
                    sequence=self._persist_sequence,
                    event_type="run.started",
                    payload={"model": str(context.get("model", ""))},
                )
            )
            return
        list_after = getattr(self.event_store, "list_after", None)
        if callable(list_after):
            existing_events = await list_after(run_id, after_sequence=0)
            self._persist_sequence = max(
                (int(event.sequence) for event in existing_events),
                default=0,
            )

    def _finish_from_existing_run(self) -> None:
        if self._existing_run_status == "cancelled":
            self._finish("cancelled", ErrorCode.CANCELLED)
        elif self._existing_run_status == "succeeded":
            self._finish("completed", None)
        elif self._existing_run_status == "failed":
            self._finish("failed", ErrorCode.PERMANENT)
        elif self._existing_run_status == "abandoned":
            self._finish("failed", ErrorCode.PERMANENT)

    async def _persist_event(self, event: RunEvent) -> None:
        if self.event_store is None or self.run_store is None:
            return
        self._persist_sequence += 1
        try:
            persisted_invocation_id = event.invocation_id
            if event.event_type == "tool_call_start":
                capability = str(event.payload.get("name", "unknown"))
                invocation_id = event.invocation_id or (
                    f"inv-{event.run_id}-{self._persist_sequence}"
                )
                self._active_invocations.setdefault(capability, []).append(invocation_id)
                await self.run_store.create_invocation(
                    run_id=event.run_id,
                    invocation_id=invocation_id,
                    sequence=self._persist_sequence,
                    capability=capability,
                    input_payload=event.payload,
                )
                persisted_invocation_id = invocation_id
            elif event.event_type == "tool_call_end" and not persisted_invocation_id:
                capability = str(event.payload.get("name", "unknown"))
                active = self._active_invocations.get(capability, [])
                if active:
                    persisted_invocation_id = active.pop(0)
            await self.event_store.append(
                RunEvent(
                    run_id=event.run_id,
                    sequence=self._persist_sequence,
                    event_type=event.event_type,
                    invocation_id=persisted_invocation_id,
                    payload=event.payload,
                )
            )
            if event.event_type == "tool_call_end" and persisted_invocation_id:
                status = str(event.payload.get("status", "failed"))
                mapped_status = (
                    "succeeded"
                    if status in {"success", "succeeded", "completed"}
                    else "timed_out"
                    if status in {"timeout", "timed_out"}
                    else "denied"
                    if status in {"denied", "policy_denied"}
                    else "cancelled"
                    if status == "cancelled"
                    else "failed"
                )
                await self.run_store.finish_invocation(
                    persisted_invocation_id,
                    mapped_status,
                    error_code=None if mapped_status == "succeeded" else mapped_status,
                )
        except Exception as exc:
            raise PersistenceHalt("interactive Run persistence failed") from exc

    async def _persist_terminal(self) -> None:
        if (
            self._terminal_persisted
            or self.run_store is None
            or self.event_store is None
            or self.terminal_result is None
        ):
            return
        self._terminal_persisted = True
        result = self.terminal_result
        status = (
            "succeeded"
            if result.status == "completed"
            else "cancelled"
            if result.status == "cancelled"
            else "failed"
        )
        try:
            self._persist_sequence += 1
            await self.event_store.append(
                RunEvent(
                    run_id=result.run_id,
                    sequence=self._persist_sequence,
                    event_type=f"run.{status}",
                    payload={
                        "error_code": result.error_code.value
                        if result.error_code
                        else None
                    },
                )
            )
            try:
                await self.run_store.transition(
                    result.run_id,
                    status,
                    error_code=result.error_code.value if result.error_code else None,
                )
            except InvalidRunTransition:
                current = await self.run_store.get(result.run_id)
                if current is None or current.status != status:
                    raise
        except Exception as exc:
            self.persistence_failure = exc
            if result.status != "failed" or result.error_code != ErrorCode.PERMANENT:
                self.terminal_result = RunResult(
                    run_id=result.run_id,
                    status="failed",
                    content=None,
                    error_code=ErrorCode.PERMANENT,
                )
            with suppress(Exception):
                await self.run_store.transition(
                    result.run_id,
                    "failed",
                    error_code=ErrorCode.PERMANENT.value,
                )

    @classmethod
    def _gateway_terminal(
        cls, result: Any
    ) -> tuple[str, ErrorCode] | None:
        if result is None or getattr(result, "status", None) == "completed":
            return None
        provider_code = str(getattr(result, "error_code", "permanent"))
        if provider_code in {"timeout"}:
            return "timeout", ErrorCode.TIMEOUT
        if provider_code in {"cancelled"}:
            return "cancelled", ErrorCode.CANCELLED
        if provider_code in {"transient", "rate_limited"}:
            return "failed", ErrorCode.TRANSIENT
        if provider_code in {"invalid_request"}:
            return "failed", ErrorCode.INVALID_REQUEST
        return "failed", ErrorCode.PERMANENT
