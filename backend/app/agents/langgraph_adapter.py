from __future__ import annotations

from typing import Any, AsyncGenerator

from app.agents.base import BaseAgent
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
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Forward streaming execution to ChatWorkflow without dropping options."""
        metadata = getattr(task, "metadata", None) or {}
        context = getattr(task, "context", None) or {}
        options = {**metadata, **context}
        async for chunk in self._workflow.stream_chat(
            model=model if model is not None else options.get("model", "gpt-3.5-turbo"),
            messages=messages if messages is not None else options.get("messages", []),
            temperature=(
                temperature if temperature is not None else options.get("temperature", 0.7)
            ),
            thread_id=thread_id if thread_id is not None else options.get("thread_id", "default"),
            speak_prompt=(
                speak_prompt if speak_prompt is not None else options.get("speak_prompt")
            ),
            deepseek_options=(
                deepseek_options
                if deepseek_options is not None
                else options.get("deepseek_options")
            ),
        ):
            yield chunk

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
