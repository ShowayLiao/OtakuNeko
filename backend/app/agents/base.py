from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Abstract agent interface.

    All agents in OtakuNeko V3 implement this interface.
    The harness runtime depends on this abstraction, not on
    concrete implementations like LangGraph.
    """

    @abstractmethod
    async def execute(self, task: Any) -> Any:
        """Execute a task and return the result."""

    @abstractmethod
    async def plan(self, task: Any) -> dict[str, Any]:
        """Generate an execution plan for the given task.

        Returns a structured plan dict that describes the steps
        the agent intends to take.
        """

    @abstractmethod
    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        """Reflect on the execution result.

        Returns a reflection dict with observations and potential
        improvements.
        """
