from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.harness.checkpoint import CheckpointStore, InMemoryCheckpointStore

__all__ = [
    "AgentTask",
    "AgentState",
    "AgentAdapter",
    "AgentRuntime",
    "StreamingAgentAdapter",
    "ChatWorkflowAdapter",
    "CheckpointStore",
    "InMemoryCheckpointStore",
]


def __getattr__(name: str):
    """Load runtime adapters lazily to keep adapter imports acyclic."""
    if name in {"AgentAdapter", "AgentRuntime", "StreamingAgentAdapter"}:
        from app.harness.runtime import (
            AgentAdapter,
            AgentRuntime,
            StreamingAgentAdapter,
        )

        return {
            "AgentAdapter": AgentAdapter,
            "AgentRuntime": AgentRuntime,
            "StreamingAgentAdapter": StreamingAgentAdapter,
        }[name]
    if name == "ChatWorkflowAdapter":
        from app.harness.adapter import ChatWorkflowAdapter

        return ChatWorkflowAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
