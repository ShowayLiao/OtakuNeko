import json
import logging
from typing import Dict, Any, List, Optional

import httpx

from app.agents.mcp.transport import MCPTransport
from app.core.logging import get_logger

logger = get_logger(__name__)

RPC_VERSION = "2.0"
CONNECT_TIMEOUT = 10.0
CALL_TIMEOUT = 30.0


class SSETransport(MCPTransport):
    def __init__(self, server_name: str, url: str,
                 headers: Dict[str, str] = None):
        self.server_name = server_name
        self.url = url
        self.headers = headers or {}
        self._client: httpx.AsyncClient = None
        self._request_id = 0
        self._connected = False

    async def connect(self) -> None:
        if self._connected:
            return

        logger.info("sse_connecting", extra={
            "server_name": self.server_name,
            "url": self.url,
        })

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=CALL_TIMEOUT),
            headers={"Content-Type": "application/json", **self.headers},
        )

        init_response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "OtakuNeko", "version": "0.1.0"},
        })

        if "error" in init_response:
            await self.close()
            raise RuntimeError(f"MCP initialize failed: {init_response['error']}")

        self._connected = True
        logger.info("sse_connected", extra={
            "server_name": self.server_name,
            "server_info": init_response.get("result", {}).get("serverInfo", {}),
        })

    async def close(self) -> None:
        self._connected = False
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        response = await self._send_request("tools/list", {})
        return response.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        if "error" in response:
            raise RuntimeError(f"MCP tool '{name}' error: {response['error']}")
        result = response.get("result", {})
        return result.get("content", result)

    async def _send_request(self, method: str, params: dict) -> dict:
        self._request_id += 1
        request_payload = {
            "jsonrpc": RPC_VERSION,
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            resp = await self._client.post(self.url, json=request_payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise RuntimeError(f"MCP call '{method}' timed out after {CALL_TIMEOUT}s")
        except httpx.HTTPError as e:
            raise RuntimeError(f"MCP call '{method}' HTTP error: {e}")
