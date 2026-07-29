import pytest
from langchain_core.tools import tool as langchain_tool

from app.agents.registry import ToolRegistry


class FakeMCPTransport:
    server_name = "fake-server"

    async def connect(self):
        pass

    async def close(self):
        pass

    async def list_tools(self):
        return [
            {
                "name": "remote_search",
                "description": "Search remote database",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        ]

    async def call_tool(self, name, arguments):
        return {"result": f"remote: {name}({arguments})"}


@langchain_tool
async def fake_local_tool(value: int) -> dict:
    """A fake local tool for testing."""
    return {"doubled": value * 2}


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(fake_local_tool)
    return reg


class TestToolRegistry:
    """Tool Step 1+2 — ToolRegistry + MCP 测试"""

    def test_register_stores_tool(self, registry):
        assert "fake_local_tool" in registry._local_tools

    def test_get_all_returns_base_tools(self, registry):
        tools = registry.get_all()
        assert len(tools) == 1
        from langchain_core.tools import BaseTool
        assert all(isinstance(t, BaseTool) for t in tools)

    def test_get_raises_keyerror_for_missing(self, registry):
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    @pytest.mark.asyncio
    async def test_get_runtime_tools_without_mcp_returns_only_local(self, registry):
        tools = await registry.get_runtime_tools()
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_get_runtime_tools_includes_mcp_tools(self, registry):
        registry.register_mcp(FakeMCPTransport())
        tools = await registry.get_runtime_tools()
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_get_all_schemas_without_mcp(self, registry):
        schemas = await registry.get_all_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert "value" in schemas[0]["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_get_all_schemas_merges_mcp(self, registry):
        registry.register_mcp(FakeMCPTransport())
        schemas = await registry.get_all_schemas()
        assert len(schemas) == 2
