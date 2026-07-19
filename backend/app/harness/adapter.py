from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from app.harness.state import AgentState


class ChatWorkflowAdapter:
    """Wraps the existing ChatWorkflow so the harness runtime can invoke it.

    Existing workflow code is unchanged — this is a thin pass-through adapter.
    """

    def __init__(self, workflow):
        self._workflow = workflow

    async def run(self, state: AgentState) -> Any:
        """Non-streaming entry point for AgentRuntime.execute()."""
        raise NotImplementedError(
            "ChatWorkflow produces streaming output; "
            "use stream() instead of run() for chat interactions."
        )

    async def stream(
        self,
        state: AgentState,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        thread_id: str = "default",
        speak_prompt: Optional[str] = None,
        deepseek_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat output through the wrapped ChatWorkflow."""
        async for chunk in self._workflow.stream_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            thread_id=thread_id,
            speak_prompt=speak_prompt,
            deepseek_options=deepseek_options,
        ):
            yield chunk

    @property
    def workflow(self):
        return self._workflow
