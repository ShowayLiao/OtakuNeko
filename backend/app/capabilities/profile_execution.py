"""Bounded pure profile computation; cancellation abandons waiting, not work."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import BoundedSemaphore
from typing import Callable, TypeVar

_T = TypeVar("_T")
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="profile-compute")
_SLOTS = BoundedSemaphore(2)


async def run_calculation(operation: Callable[[], _T]) -> _T:
    """Keep capacity until the actual worker exits, even after caller timeout.

    Operations receive only owned data snapshots, never sessions or clients.
    Admission is asynchronous; no executor thread waits for another slot.
    """
    while not _SLOTS.acquire(blocking=False):
        await asyncio.sleep(0.01)

    def run() -> _T:
        try:
            return operation()
        finally:
            _SLOTS.release()

    try:
        future = asyncio.get_running_loop().run_in_executor(_EXECUTOR, partial(run))
    except BaseException:
        _SLOTS.release()
        raise

    # A timed-out caller cannot cancel queued execution and leak its slot.
    # Consume late errors without logging raw diagnostics to the event loop.
    future.add_done_callback(
        lambda done: None if done.cancelled() else done.exception()
    )
    return await asyncio.shield(future)
