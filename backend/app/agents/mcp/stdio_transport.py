import asyncio
import json
from typing import Dict, Any, List

from app.agents.mcp.transport import MCPTransport
from app.core.logging import get_logger

logger = get_logger(__name__)

RPC_VERSION = "2.0"
CONNECT_TIMEOUT = 10.0
CALL_TIMEOUT = 30.0


class StdioTransport(MCPTransport):
    def __init__(
        self,
        server_name: str,
        command: str,
        args: List[str] | None = None,
        env: Dict[str, str] | None = None,
    ):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return

        logger.info(
            "stdio_connecting",
            extra={
                "server_name": self.server_name,
                "command": self.command,
            },
        )

        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, **self.env},
        )

        self._reader_task = asyncio.create_task(self._read_loop())
        self._connected = True

        try:
            init_response = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "OtakuNeko", "version": "0.1.0"},
                },
            )
            if "error" in init_response:
                raise RuntimeError(f"MCP initialize failed: {init_response['error']}")
            await self._send_notification("notifications/initialized", {})
        except BaseException:
            await self.close()
            raise

        logger.info(
            "stdio_connected",
            extra={
                "server_name": self.server_name,
                "server_info": init_response.get("result", {}).get("serverInfo", {}),
            },
        )

    async def close(self) -> None:
        self._connected = False
        reader_task = self._reader_task
        self._reader_task = None
        if reader_task is not None:
            reader_task.cancel()
        if self._process:
            try:
                if self._process.stdin is not None:
                    self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.kill()
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except Exception:
                pass
            self._process = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("Transport closed"))
        self._pending.clear()

    async def list_tools(self) -> List[Dict[str, Any]]:
        response = await self._send_request("tools/list", {})
        return response.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        response = await self._send_request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )
        result = response.get("result", {})
        if "error" in response:
            raise RuntimeError(f"MCP tool '{name}' error: {response['error']}")
        return result.get("content", result)

    async def _send_request(self, method: str, params: dict) -> dict:
        process = self._process
        if not self._connected or process is None or process.stdin is None:
            raise RuntimeError("MCP transport is not connected")
        self._request_id += 1
        msg_id = self._request_id

        request = {
            "jsonrpc": RPC_VERSION,
            "id": msg_id,
            "method": method,
            "params": params,
        }

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        try:
            data = json.dumps(request) + "\n"
            process.stdin.write(data.encode("utf-8"))
            await process.stdin.drain()
            return await asyncio.wait_for(fut, timeout=CALL_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise RuntimeError(f"MCP call '{method}' timed out after {CALL_TIMEOUT}s")
        finally:
            self._pending.pop(msg_id, None)

    async def _send_notification(self, method: str, params: dict) -> None:
        process = self._process
        if not self._connected or process is None or process.stdin is None:
            raise RuntimeError("MCP transport is not connected")
        request = {
            "jsonrpc": RPC_VERSION,
            "method": method,
            "params": params,
        }
        process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        await process.stdin.drain()

    async def _read_loop(self) -> None:
        try:
            while self._connected:
                process = self._process
                if process is None or process.stdout is None:
                    break
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    pending = self._pending[msg_id]
                    if not pending.done():
                        pending.set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(
                "stdio_read_failed",
                extra={
                    "server_name": self.server_name,
                    "error_category": type(exc).__name__,
                },
            )
        finally:
            self._connected = False
            for pending in self._pending.values():
                if not pending.done():
                    pending.set_exception(RuntimeError("MCP transport closed"))
