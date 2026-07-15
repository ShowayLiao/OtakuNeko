from typing import Dict, Any, List
from langchain_core.tools import tool as langchain_tool, BaseTool


class MCPToolAdapter:
    """将 MCP tool schema 转换为 LangChain 兼容格式"""

    @staticmethod
    def to_openai_function(tool_def: Dict) -> Dict:
        params = tool_def.get("inputSchema", {})
        return {
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": params.get("properties", {}),
                    "required": params.get("required", []),
                },
            },
        }

    @staticmethod
    def to_langchain_tool(tool_def: Dict, transport) -> BaseTool:
        name = tool_def["name"]
        desc = tool_def.get("description", "")
        input_schema = tool_def.get("inputSchema", {})

        async def _call_tool(**kwargs):
            return await transport.call_tool(name, kwargs)

        _call_tool.__name__ = name
        _call_tool.__doc__ = desc

        tool_instance = langchain_tool(_call_tool)
        tool_instance.name = name
        tool_instance.description = desc
        return tool_instance
