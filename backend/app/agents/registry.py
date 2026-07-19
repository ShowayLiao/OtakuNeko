from typing import List, Dict, Any
from langchain_core.tools import BaseTool


class ToolRegistry:
    def __init__(self):
        self._local_tools: Dict[str, BaseTool] = {}
        self._mcp_clients: List = []

    def register(self, tool: BaseTool) -> None:
        self._local_tools[tool.name] = tool

    def register_all(self, tools: List[BaseTool]) -> None:
        for t in tools:
            self.register(t)

    def register_mcp(self, client) -> None:
        self._mcp_clients.append(client)

    def get_all(self) -> List[BaseTool]:
        return list(self._local_tools.values())

    def get(self, name: str) -> BaseTool:
        if name not in self._local_tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._local_tools[name]

    def list_names(self) -> List[str]:
        return list(self._local_tools.keys())

    async def get_runtime_tools(self) -> List[BaseTool]:
        from app.agents.mcp.adapter import MCPToolAdapter

        tools = list(self._local_tools.values())
        for client in self._mcp_clients:
            for tool_def in await client.list_tools():
                tools.append(MCPToolAdapter.to_langchain_tool(tool_def, client))
        return tools

    async def get_all_schemas(self) -> List[Dict[str, Any]]:
        from app.agents.mcp.adapter import MCPToolAdapter

        schemas = []
        for tool in self._local_tools.values():
            if hasattr(tool, "args_schema") and tool.args_schema:
                parameters = tool.args_schema.model_json_schema()
                parameters.pop("title", None)
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                })

        for client in self._mcp_clients:
            for tool_def in await client.list_tools():
                schemas.append(MCPToolAdapter.to_openai_function(tool_def))

        return schemas
