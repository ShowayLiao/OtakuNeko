import asyncio
import json
import logging
from typing import Dict, Any, List

from app.agents.mcp.transport import MCPTransport
from app.core.logging import get_logger

logger = get_logger(__name__)

RPC_VERSION = "2.0"
CONNECT_TIMEOUT = 10.0
CALL_TIMEOUT = 30.0


class StdioTransport(MCPTransport):
    def __init__(self, server_name: str, command: str, args: List[str] = None,
                 env: Dict[str, str] = None):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: asyncio.subprocess.Process = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task = None
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return

        logger.info("stdio_connecting", extra={
            "server_name": self.server_name,
            "command": self.command,
        })

        self._process = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, **self.env},
        )

        self._reader_task = asyncio.create_task(self._read_loop())
        self._connected = True

        init_response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "OtakuNeko", "version": "0.1.0"},
        })

        if "error" in init_response:
            await self.close()
            raise RuntimeError(f"MCP initialize failed: {init_response['error']}")

        logger.info("stdio_connected", extra={
            "server_name": self.server_name,
            "server_info": init_response.get("result", {}).get("serverInfo", {}),
        })

    async def close(self) -> None:
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._process:
            try:
                self._process.stdin.close()
                self._process.stdout.close() if self._process.stdout else None
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
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        result = response.get("result", {})
        if "error" in response:
            raise RuntimeError(f"MCP tool '{name}' error: {response['error']}")
        return result.get("content", result)

    async def _send_request(self, method: str, params: dict) -> dict:
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

        data = json.dumps(request) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=CALL_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise RuntimeError(f"MCP call '{method}' timed out after {CALL_TIMEOUT}s")
        finally:
            self._pending.pop(msg_id, None)

    async def _read_loop(self):
        try:
            while self._connected:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    self._pending[msg_id].set_result(msg)
        except (asyncio.CancelledError, Exception):
            pass
