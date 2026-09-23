from __future__ import annotations

from typing import Dict, List

from app.agents.base import BaseAgent


class AgentRegistry:
    """Registry for agent discovery.

    Stores named agent instances and provides lookup. Does NOT perform
    routing or dispatching — that responsibility belongs to a future
    AgentRouter (RFC-106 Phase 5).
    """

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, name: str, agent: BaseAgent) -> None:
        """Register an agent under a unique name."""
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        self._agents[name] = agent

    def get(self, name: str) -> BaseAgent:
        """Retrieve a registered agent by name."""
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' not found in registry")
        return self._agents[name]

    def list_agents(self) -> List[str]:
        """Return names of all registered agents."""
        return list(self._agents.keys())

    def unregister(self, name: str) -> None:
        """Remove an agent from the registry."""
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' not found in registry")
        del self._agents[name]
