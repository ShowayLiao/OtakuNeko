import pytest
from app.agents.mcp.adapter import MCPToolAdapter


class TestMCPToolAdapter:
    """Tool Step 2 — MCPToolAdapter schema 转换测试"""

    def test_to_openai_function_returns_valid_format(self):
        mcp_def = {
            "name": "calc",
            "description": "Calculate something",
            "inputSchema": {
                "type": "object",
                "properties": {"expr": {"type": "string"}},
                "required": ["expr"],
            },
        }
        schema = MCPToolAdapter.to_openai_function(mcp_def)
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calc"
        assert "expr" in schema["function"]["parameters"]["properties"]

    def test_to_langchain_tool_returns_base_tool(self):
        from langchain_core.tools import BaseTool

        mcp_def = {
            "name": "remote_search",
            "description": "Search remote database",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }

        transport = type("Fake", (), {
            "call_tool": lambda self, name, args: {"result": f"{name}: {args}"},
            "server_name": "fake",
        })()

        tool = MCPToolAdapter.to_langchain_tool(mcp_def, transport)
        assert isinstance(tool, BaseTool)
        assert tool.name == "remote_search"
        assert "query" in tool.args_schema.model_fields
        assert tool.args_schema.model_fields["query"].is_required()

    def test_to_openai_function_empty_schema(self):
        mcp_def = {"name": "noop", "description": "", "inputSchema": {"type": "object"}}
        schema = MCPToolAdapter.to_openai_function(mcp_def)
        assert schema["function"]["name"] == "noop"
