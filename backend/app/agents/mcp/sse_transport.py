from typing import Dict, Any, List

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
        self._session_id: str | None = None

    async def connect(self) -> None:
        if self._connected:
            return

        logger.info("sse_connecting", extra={
            "server_name": self.server_name,
        })

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=CALL_TIMEOUT),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **self.headers,
            },
        )

        init_response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "OtakuNeko", "version": "0.1.0"},
        })

        if "error" in init_response:
            await self.close()
            raise RuntimeError(f"MCP initialize failed: {init_response['error']}")

        await self._send_notification("notifications/initialized", {})
        self._connected = True
        logger.info("sse_connected", extra={
            "server_name": self.server_name,
            "server_info": init_response.get("result", {}).get("serverInfo", {}),
        })

    async def close(self) -> None:
        self._connected = False
        self._session_id = None
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
            headers = {"Mcp-Session-Id": self._session_id} if self._session_id else {}
            resp = await self._client.post(self.url, json=request_payload, headers=headers)
            resp.raise_for_status()
            session_id = resp.headers.get("Mcp-Session-Id")
            if session_id:
                self._session_id = session_id
            return resp.json()
        except httpx.TimeoutException:
            raise RuntimeError(f"MCP call '{method}' timed out after {CALL_TIMEOUT}s")
        except httpx.HTTPError as e:
            raise RuntimeError(f"MCP call '{method}' HTTP error: {e}")

    async def _send_notification(self, method: str, params: dict) -> None:
        headers = {"Mcp-Session-Id": self._session_id} if self._session_id else {}
        try:
            resp = await self._client.post(
                self.url,
                json={"jsonrpc": RPC_VERSION, "method": method, "params": params},
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"MCP notification '{method}' HTTP error: {e}")
