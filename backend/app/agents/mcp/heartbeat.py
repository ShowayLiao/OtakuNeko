import asyncio
import time
from typing import Dict, List
from dataclasses import dataclass, field

from app.agents.mcp.transport import MCPTransport
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_HEARTBEAT_INTERVAL = 15.0
DEFAULT_HEARTBEAT_TIMEOUT = 5.0


@dataclass
class HeartbeatStatus:
    last_seen: float = field(default_factory=time.monotonic)
    alive: bool = True
    consecutive_misses: int = 0


class MCPHeartbeat:
    def __init__(self,
                 interval: float = DEFAULT_HEARTBEAT_INTERVAL,
                 timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
                 max_misses: int = 3):
        self._interval = interval
        self._timeout = timeout
        self._max_misses = max_misses
        self._status: Dict[str, HeartbeatStatus] = {}
        self._task: asyncio.Task = None
        self._running = False
        self._on_dead_callback = None

    def on_dead(self, callback):
        self._on_dead_callback = callback

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("heartbeat_started", extra={
            "interval_s": self._interval,
            "timeout_s": self._timeout,
        })

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._status.clear()
        logger.info("heartbeat_stopped")

    def register(self, name: str):
        self._status[name] = HeartbeatStatus()

    def unregister(self, name: str):
        self._status.pop(name, None)

    def mark_alive(self, name: str):
        if name in self._status:
            self._status[name].last_seen = time.monotonic()
            self._status[name].alive = True
            self._status[name].consecutive_misses = 0

    async def _loop(self):
        while self._running:
            await asyncio.sleep(self._interval)
            now = time.monotonic()
            for name, status in list(self._status.items()):
                elapsed = now - status.last_seen
                if elapsed > self._timeout:
                    status.alive = False
                    status.consecutive_misses += 1
                    logger.warning("heartbeat_miss", extra={
                        "server_name": name,
                        "elapsed_s": round(elapsed, 1),
                        "consecutive_misses": status.consecutive_misses,
                    })
                    if status.consecutive_misses >= self._max_misses and self._on_dead_callback:
                        logger.error("heartbeat_dead", extra={
                            "server_name": name,
                            "consecutive_misses": status.consecutive_misses,
                        })
                        await self._on_dead_callback(name)
