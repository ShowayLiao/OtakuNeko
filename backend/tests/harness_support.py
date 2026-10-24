"""Shared harness-test policy: read-only failures are observations, not terminals."""

from __future__ import annotations

from typing import Any

from app.harness.task import AgentTask

HARNESS_TASK_POLICY: dict[str, Any] = {"continue_on_read_only_error": True}


def harness_task(*, user_id: int, goal: str, metadata: dict[str, Any]) -> AgentTask:
    """Build a harness-test task with the fail-continue policy applied."""
    return AgentTask(
        user_id=user_id,
        goal=goal,
        task_metadata={**metadata, **HARNESS_TASK_POLICY},
    )
