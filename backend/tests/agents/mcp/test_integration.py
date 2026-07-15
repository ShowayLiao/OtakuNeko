import pytest
from unittest.mock import AsyncMock

from app.agents.mcp.adapter import MCPToolAdapter
from app.agents.mcp.connection_pool import MCPConnectionPool


class FakeTransport:
    def __init__(self, name, tools=None):
        self.server_name = name
        self._tools = tools or []
        self.connect = AsyncMock()
        self.close = AsyncMock()

    def list_tools(self):
        return self._tools

    async def call_tool(self, name, arguments):
        return {"result": f"called {name} with {arguments}"}


class TestMCPIntegration:
    """MCP + ToolRegistry + ConnectionPool 集成测试"""

    @pytest.mark.asyncio
    async def test_adapter_wraps_transport_tool_correctly(self):
        transport = FakeTransport("filesystem", [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        ])

        tool = MCPToolAdapter.to_langchain_tool(
            transport.list_tools()[0],
            transport,
        )

        assert tool.name == "read_file"
        assert tool.description == "Read a file"

    @pytest.mark.asyncio
    async def test_pool_registers_and_reports_healthy(self):
        pool = MCPConnectionPool()
        transport = FakeTransport("healthy-srv")

        await pool.register(transport)
        assert "healthy-srv" in pool._transports
        assert pool._transports["healthy-srv"].is_healthy
        await pool.stop()
