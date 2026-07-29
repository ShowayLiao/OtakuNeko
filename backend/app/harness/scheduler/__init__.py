"""Scheduler runtime — PROACTIVE-001 Step 02.

A single-process in-memory scheduler that polls due tasks, claims them
through expiring leases, and dispatches runs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
from typing import Any, Callable

from app.core.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_LEASE_DURATION_SECONDS = 60


class Scheduler:
    """Single-process scheduler with lease-based task claiming.

    Usage::

        async def handler(task_def, run) -> None: ...

        scheduler = Scheduler(claim_fn, handler)
        await scheduler.start(interval=5)
        # ... later ...
        await scheduler.stop()
    """

    def __init__(
        self,
        claim_fn: Callable[[int], list[tuple[Any, Any]]],
        handler: Callable[[Any, Any], Any],
        lease_seconds: int = _LEASE_DURATION_SECONDS,
        *,
        clock: Callable[[], datetime] | None = None,
        shutdown_timeout: float = 30,
    ) -> None:
        self._claim_fn = claim_fn
        self._handler = handler
        self._lease_seconds = lease_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._clock = clock or _utc_now
        self._shutdown_timeout = shutdown_timeout
        self._active: set[asyncio.Task[None]] = set()
        self._stop_event = asyncio.Event()

    async def start(self, interval: int = 5) -> None:
        """Start the scheduler polling loop."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop(interval))
        logger.info("scheduler_started", extra={"interval": interval})

    async def stop(self) -> None:
        """Stop the scheduler and wait for the current poll to finish."""
        self._running = False
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self._shutdown_timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._active:
            _, pending = await asyncio.wait(
                self._active,
                timeout=self._shutdown_timeout,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        logger.info("scheduler_stopped")

    async def poll_once(self) -> int:
        """Claim and dispatch one batch; useful for deterministic tests."""
        try:
            result = self._claim_fn(self._lease_seconds)
        except Exception:
            logger.exception("scheduler_poll_failed")
            return 0
        runs = await result if inspect.isawaitable(result) else result
        for task_def, run in _pairs(runs):
            task = asyncio.create_task(self._run_with_lease(task_def, run))
            self._active.add(task)
            task.add_done_callback(self._active.discard)
        return len(runs)

    async def _poll_loop(self, interval: int) -> None:
        while self._running:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("scheduler_poll_failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _run_with_lease(self, task_def: Any, run: Any) -> None:
        try:
            await self._handler(task_def, run)
        except Exception:
            logger.exception("scheduler_run_failed")


def _pairs(runs: Any) -> list[tuple[Any, Any]]:
    return [(item.task_def, item.run) if hasattr(item, "task_def") else item for item in runs]
