import pytest

from app.agents.mcp.adapter import MCPToolAdapter
from app.agents.mcp.connection_pool import MCPConnectionPool
from app.agents.mcp.transport import MCPTransport


class FakeTransport(MCPTransport):
    def __init__(self, name, tools=None):
        self.server_name = name
        self._tools = tools or []
        self.connect_calls = 0
        self.close_calls = 0

    async def connect(self):
        self.connect_calls += 1

    async def close(self):
        self.close_calls += 1

    async def list_tools(self):
        return self._tools

    async def call_tool(self, name, arguments):
        return {"result": f"called {name} with {arguments}"}


class TestMCPIntegration:
    """MCP + ToolRegistry + ConnectionPool 集成测试"""

    @pytest.mark.asyncio
    async def test_adapter_wraps_transport_tool_correctly(self):
        transport = FakeTransport(
            "filesystem",
            [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            ],
        )

        tool = MCPToolAdapter.to_langchain_tool(
            (await transport.list_tools())[0],
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
