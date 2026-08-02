from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any, AsyncGenerator

from app.agents.base import BaseAgent
from app.harness.budget import CancellationToken
from app.harness.contracts import RunEvent
from app.trace import TraceEventType
from app.trace.recorder import (
    TraceRecorder,
    current_trace_recorder,
    safe_argument_shape,
)


_ADAPTABLE_EVENT_TYPES = {
    "thinking_start",
    "thinking_end",
    "tool_call_start",
    "tool_call_end",
    "message_start",
    "message_chunk",
    "message_end",
    "model_decision",
    "tool_requested",
    "error",
}


def adapt_langgraph_event(
    event: dict[str, Any],
    *,
    run_id: str,
    sequence: int,
) -> RunEvent | None:
    """Convert one legacy LangGraph chunk into a safe internal RunEvent."""
    event_type = event.get("type")
    if event_type not in _ADAPTABLE_EVENT_TYPES:
        return None

    invocation_id = event.get("id")
    payload: dict[str, Any] = {}
    if event_type == "tool_call_start":
        inputs = event.get("inputs")
        payload = {
            "name": str(event.get("name", "unknown")),
            "argument_keys": sorted(inputs) if isinstance(inputs, dict) else [],
        }
    elif event_type == "tool_call_end":
        payload = {
            "name": str(event.get("name", "unknown")),
            "status": str(event.get("status", "unknown")),
        }
        if isinstance(event.get("duration_ms"), (int, float)):
            payload["duration_ms"] = event["duration_ms"]
    elif event_type == "message_chunk":
        payload = {"content": str(event.get("content", ""))}
    elif event_type == "error":
        payload = {"error_code": "permanent"}
    elif event_type == "model_decision":
        decision = event.get("decision")
        payload = {
            "action": decision.get("action") if isinstance(decision, dict) else "unknown",
            "capability": decision.get("capability") if isinstance(decision, dict) else None,
            "capability_version": (
                decision.get("capability_version") if isinstance(decision, dict) else None
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


def adapt_langgraph_events(
    events: list[dict[str, Any]],
    *,
    run_id: str,
) -> list[RunEvent]:
    """Convert recognized legacy chunks with a stable contiguous sequence."""
    adapted: list[RunEvent] = []
    for event in events:
        converted = adapt_langgraph_event(
            event,
            run_id=run_id,
            sequence=len(adapted) + 1,
        )
        if converted is not None:
            adapted.append(converted)
    return adapted


class LangGraphAdapter(BaseAgent):
    """Adapter that implements the BaseAgent interface on top of ChatWorkflow.

    Wraps the existing LangGraph ChatWorkflow without modifying its graph logic.
    """

    def __init__(self, workflow: Any) -> None:
        self._workflow = workflow

    async def execute(self, task: Any) -> Any:
        """Execute a task synchronously (non-streaming).

        Collects all streamed chunks and returns the assembled result.
        """
        chunks: list[dict[str, Any]] = []
        result_text: str = ""
        tool_calls: list[dict[str, Any]] = []

        async for chunk in self.stream(task):
            chunks.append(chunk)
            if chunk.get("type") == "message_chunk":
                result_text += chunk.get("content", "")
            elif chunk.get("type") == "tool_call_end":
                tool_calls.append(chunk)

        return {
            "text": result_text,
            "tool_calls": tool_calls,
            "all_events": chunks,
        }

    async def stream(
        self,
        task: Any,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        thread_id: str | None = None,
        speak_prompt: str | None = None,
        deepseek_options: dict[str, Any] | None = None,
        cancellation: CancellationToken | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Forward streaming execution to ChatWorkflow without dropping options."""
        metadata = getattr(task, "metadata", None) or {}
        context = getattr(task, "context", None) or {}
        options = {**metadata, **context}
        selected_model = (
            model if model is not None else options.get("model", "gpt-3.5-turbo")
        )
        active_nodes: dict[str, tuple[Any, float]] = {}
        active_tools: dict[str, tuple[Any, float, str]] = {}
        terminal_status = "completed"
        try:
            workflow_kwargs = {
                "model": selected_model,
                "messages": messages if messages is not None else options.get("messages", []),
                "temperature": (
                    temperature
                    if temperature is not None
                    else options.get("temperature", 0.7)
                ),
                "thread_id": (
                    thread_id
                    if thread_id is not None
                    else options.get("thread_id", "default")
                ),
                "speak_prompt": (
                    speak_prompt
                    if speak_prompt is not None
                    else options.get("speak_prompt")
                ),
                "deepseek_options": (
                    deepseek_options
                    if deepseek_options is not None
                    else options.get("deepseek_options")
                ),
            }
            if cancellation is not None:
                workflow_kwargs["cancellation"] = cancellation
            async for chunk in self._workflow.stream_chat(
                **workflow_kwargs,
            ):
                recorder = current_trace_recorder()
                if recorder is not None:
                    self._record_workflow_chunk(
                        recorder,
                        chunk,
                        active_nodes,
                        active_tools,
                        selected_model,
                    )
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            terminal_status = "cancelled"
            raise
        except asyncio.TimeoutError:
            terminal_status = "timeout"
            raise
        except Exception:
            terminal_status = "failed"
            raise
        finally:
            recorder = current_trace_recorder()
            if recorder is not None:
                self._close_open_spans(
                    recorder,
                    active_nodes,
                    active_tools,
                    selected_model,
                    terminal_status,
                )

    @staticmethod
    def _record_workflow_chunk(
        recorder: TraceRecorder,
        chunk: dict[str, Any],
        active_nodes: dict[str, tuple[Any, float]],
        active_tools: dict[str, tuple[Any, float, str]],
        model: str,
    ) -> None:
        chunk_type = chunk.get("type")
        if chunk_type == "route_decision":
            recorder.record(
                TraceEventType.ROUTING_DECISION,
                "langgraph.route",
                {
                    "route": chunk.get("route"),
                    "agent": chunk.get("agent"),
                    "confidence": chunk.get("confidence"),
                },
            )
        elif chunk_type in {"thinking_start", "message_start"}:
            node = "think" if chunk_type == "thinking_start" else "speak"
            if node not in active_nodes:
                active_nodes[node] = (
                    recorder.record(
                        TraceEventType.NODE_START,
                        f"langgraph.{node}",
                        {"node": node},
                    ),
                    monotonic(),
                )
        elif chunk_type in {"thinking_end", "message_end"}:
            node = "think" if chunk_type == "thinking_end" else "speak"
            start = active_nodes.pop(node, None)
            parent_id = start[0].event_id if start is not None else None
            duration_ms = (monotonic() - start[1]) * 1000 if start else 0
            recorder.record(
                TraceEventType.MODEL_CALL,
                f"model.{node}",
                {"node": node, "model": model},
                parent_event_id=parent_id,
                duration_ms=duration_ms,
            )
            recorder.record(
                TraceEventType.NODE_END,
                f"langgraph.{node}",
                {"node": node},
                parent_event_id=parent_id,
                duration_ms=duration_ms,
            )
        elif chunk_type == "tool_call_start":
            tool_id = str(chunk.get("id", "unknown"))
            tool_name = str(chunk.get("name", "unknown"))
            active_tools[tool_id] = (
                recorder.record(
                    TraceEventType.TOOL_CALL_START,
                    f"tool.{tool_name}",
                    {
                        "tool": tool_name,
                        "argument_shape": safe_argument_shape(
                            chunk.get("inputs", {})
                        ),
                    },
                ),
                monotonic(),
                tool_name,
            )
        elif chunk_type == "tool_call_end":
            tool_id = str(chunk.get("id", "unknown"))
            start = active_tools.pop(tool_id, None)
            tool_name = str(chunk.get("name", start[2] if start else "unknown"))
            status = "completed" if chunk.get("status") == "success" else "failed"
            duration_ms = (
                float(chunk["duration_ms"])
                if isinstance(chunk.get("duration_ms"), (int, float))
                else ((monotonic() - start[1]) * 1000 if start else 0)
            )
            recorder.record(
                TraceEventType.TOOL_CALL_END,
                f"tool.{tool_name}",
                {
                    "tool": tool_name,
                    "result_status": chunk.get("status", "unknown"),
                },
                status=status,
                parent_event_id=start[0].event_id if start else None,
                duration_ms=duration_ms,
            )
        elif chunk_type == "error":
            recorder.record(
                TraceEventType.FAILURE,
                "langgraph.stream_chat",
                {"error_category": "graph_error"},
                status="failed",
            )

    @staticmethod
    def _close_open_spans(
        recorder: TraceRecorder,
        active_nodes: dict[str, tuple[Any, float]],
        active_tools: dict[str, tuple[Any, float, str]],
        model: str,
        status: str,
    ) -> None:
        for node, (start_event, started) in list(active_nodes.items()):
            duration_ms = (monotonic() - started) * 1000
            recorder.record(
                TraceEventType.MODEL_CALL,
                f"model.{node}",
                {"node": node, "model": model, "terminal": status},
                status=status,
                parent_event_id=start_event.event_id,
                duration_ms=duration_ms,
            )
            recorder.record(
                TraceEventType.NODE_END,
                f"langgraph.{node}",
                {"node": node, "outcome": status},
                status=status,
                parent_event_id=start_event.event_id,
                duration_ms=duration_ms,
            )
        active_nodes.clear()
        for _, (start_event, started, tool_name) in list(active_tools.items()):
            recorder.record(
                TraceEventType.TOOL_CALL_END,
                f"tool.{tool_name}",
                {"tool": tool_name, "result_status": status},
                status=status,
                parent_event_id=start_event.event_id,
                duration_ms=(monotonic() - started) * 1000,
            )
        active_tools.clear()

    async def plan(self, task: Any) -> dict[str, Any]:
        """Generate an execution plan by introspecting the task goal."""
        goal = task.goal if hasattr(task, "goal") else str(task)
        return {
            "goal": goal,
            "steps": [
                "Analyze user intent",
                "Gather relevant information via tools",
                "Synthesize response",
            ],
            "estimated_tools": [],
        }

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        """Reflect on the execution result."""
        return {
            "goal_achieved": result is not None,
            "observations": [
                "Task executed through LangGraph workflow",
                f"Result length: {len(str(result))} chars",
            ],
        }

    @property
    def workflow(self) -> Any:
        return self._workflow
