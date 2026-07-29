import asyncio
import time
from typing import Dict
from dataclasses import dataclass, field

from app.agents.mcp.transport import MCPTransport
from app.core.logging import get_logger
from app.trace import TraceEventType
from app.trace.recorder import current_trace_recorder

logger = get_logger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_HEALTH_CHECK_INTERVAL = 30.0


@dataclass
class PooledTransport:
    transport: MCPTransport
    last_used: float = field(default_factory=time.monotonic)
    is_healthy: bool = True
    fail_count: int = 0


class MCPConnectionPool:
    def __init__(self,
                 max_retries: int = DEFAULT_MAX_RETRIES,
                 retry_delay: float = DEFAULT_RETRY_DELAY,
                 health_check_interval: float = DEFAULT_HEALTH_CHECK_INTERVAL):
        self._transports: Dict[str, PooledTransport] = {}
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._health_check_interval = health_check_interval
        self._health_task: asyncio.Task = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info("connection_pool_started", extra={
            "transport_count": len(self._transports),
            "health_interval_s": self._health_check_interval,
        })

    async def stop(self):
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None

        for name, pt in list(self._transports.items()):
            try:
                await pt.transport.close()
            except Exception:
                pass

        self._transports.clear()
        logger.info("connection_pool_stopped")

    async def register(self, transport: MCPTransport) -> None:
        name = transport.server_name
        if name in self._transports:
            await self._disconnect(name)

        self._transports[name] = PooledTransport(transport=transport)
        await self._connect_with_retry(name)
        logger.info("transport_registered", extra={"server_name": name})

    async def unregister(self, name: str) -> None:
        await self._disconnect(name)

    async def call_tool(self, server_name: str, tool_name: str,
                        arguments: dict) -> dict:
        pt = self._transports.get(server_name)
        if not pt:
            raise RuntimeError(f"Transport '{server_name}' not found")

        if not pt.is_healthy:
            await self._connect_with_retry(server_name)
            pt = self._transports[server_name]

        t0 = time.perf_counter()
        try:
            result = await pt.transport.call_tool(tool_name, arguments)
            duration_ms = (time.perf_counter() - t0) * 1000
            pt.fail_count = 0
            pt.last_used = time.monotonic()

            logger.info("mcp_tool_called", extra={
                "server_name": server_name,
                "tool_name": tool_name,
                "duration_ms": round(duration_ms, 2),
                "success": True,
            })
            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            pt.fail_count += 1
            if pt.fail_count >= self._max_retries:
                pt.is_healthy = False

            logger.error("mcp_tool_failed", extra={
                "server_name": server_name,
                "tool_name": tool_name,
                "duration_ms": round(duration_ms, 2),
                "error": str(e),
                "fail_count": pt.fail_count,
            })
            raise

    async def _connect_with_retry(self, name: str) -> None:
        pt = self._transports.get(name)
        if not pt:
            return

        for attempt in range(1, self._max_retries + 1):
            try:
                await pt.transport.connect()
                pt.is_healthy = True
                pt.fail_count = 0
                logger.info("reconnect_success", extra={
                    "server_name": name,
                    "attempt": attempt,
                })
                return
            except Exception as e:
                logger.warning("reconnect_failed", extra={
                    "server_name": name,
                    "attempt": attempt,
                    "max_retries": self._max_retries,
                    "error": str(e),
                })
                if attempt < self._max_retries:
                    recorder = current_trace_recorder()
                    if recorder is not None:
                        recorder.record(
                            TraceEventType.RETRY,
                            "mcp.connect",
                            {
                                "server": name,
                                "attempt": attempt + 1,
                                "max_attempts": self._max_retries,
                                "error_category": type(e).__name__,
                            },
                        )
                    await asyncio.sleep(self._retry_delay * attempt)

        logger.error("reconnect_exhausted", extra={
            "server_name": name,
            "max_retries": self._max_retries,
        })
        raise RuntimeError(f"Failed to connect '{name}' after {self._max_retries} retries")

    async def _disconnect(self, name: str) -> None:
        pt = self._transports.pop(name, None)
        if pt:
            try:
                await pt.transport.close()
            except Exception:
                pass
            logger.info("transport_disconnected", extra={"server_name": name})

    async def _health_check_loop(self):
        while self._running:
            await asyncio.sleep(self._health_check_interval)
            for name, pt in list(self._transports.items()):
                if not pt.is_healthy:
                    try:
                        await self._connect_with_retry(name)
                    except Exception:
                        pass
