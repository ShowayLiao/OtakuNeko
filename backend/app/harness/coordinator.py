"""Single in-memory Run Coordinator for interactive agent streams."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from app.agents.langgraph_adapter import adapt_langgraph_event
from app.harness.budget import (
    BudgetExceededError,
    CancellationToken,
    DeadlineExceededError,
    RunCancellationError,
    RunBudget,
)
from app.harness.contracts import ErrorCode, RunEvent, RunResult
from app.harness.model_gateway import ModelGateway
from app.harness.result import AgentResult
from app.harness.state import AgentState
from app.harness.task import AgentTask


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
    ) -> None:
        self.adapter = adapter
        self.model_gateway = model_gateway
        self.max_model_calls = max_model_calls
        self._fallback_from_result = fallback_from_result
        self.events: list[RunEvent] = []
        self.terminal_result: RunResult | None = None
        self.failure: BaseException | None = None
        self.budget: RunBudget | None = None
        self.cancellation: CancellationToken | None = None
        self._pending_chunks: list[dict[str, Any]] = []

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
            self.cancellation.raise_if_cancelled()
            self.budget.check_deadline()
            adapter_stream = getattr(self.adapter, "stream", None)
            if adapter_stream is None:
                raise TypeError("The configured adapter does not support streaming")
            iterator = adapter_stream(execution_state, **adapter_context).__aiter__()

            while self.terminal_result is None:
                self.cancellation.raise_if_cancelled()
                self.budget.check_deadline()
                try:
                    chunk = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=self.budget.remaining_seconds(),
                    )
                except StopAsyncIteration:
                    break

                if not isinstance(chunk, dict):
                    chunk = {"type": "message_chunk", "content": str(chunk)}
                event = self._record_event(chunk, run_id)
                if event is not None:
                    self._account_event(event)

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

        if self.terminal_result is None:
            self._finish("completed", None)
        # The result is yielded exactly once, even when the adapter emitted a
        # duplicate or contradictory terminal chunk.
        yield self.terminal_result

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
                content = await self.model_gateway.synthesize(
                    goal=task.goal,
                    messages=context.get("messages") or task.metadata.get("messages", []),
                    results=execution_results,
                    model_calls_used=synthesis_used + 1,
                )
                gateway_result = getattr(self.model_gateway, "last_result", None)
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
                gateway_result = getattr(self.model_gateway, "last_result", None)
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
        converted = adapt_langgraph_event(
            chunk,
            run_id=run_id,
            sequence=sequence,
        )
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
