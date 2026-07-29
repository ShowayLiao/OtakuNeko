from typing import Any, Dict, Optional, Type

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, create_model

from app.trace import TraceEventType
from app.trace.recorder import safe_argument_shape, trace_span

_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class MCPToolAdapter:
    """Convert MCP tool definitions into explicit LangChain contracts."""

    @staticmethod
    def to_openai_function(tool_def: Dict[str, Any]) -> Dict[str, Any]:
        params = tool_def.get("inputSchema", {}) or {}
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
    def to_langchain_tool(tool_def: Dict[str, Any], transport) -> BaseTool:
        name = tool_def["name"]
        desc = tool_def.get("description", "")
        input_schema = tool_def.get("inputSchema", {}) or {}
        args_schema = MCPToolAdapter._args_schema(name, input_schema)

        async def _call_tool(**kwargs):
            async with trace_span(
                TraceEventType.MCP_CALL,
                name,
                {"argument_shape": safe_argument_shape(kwargs)},
            ) as event:
                result = await transport.call_tool(name, kwargs)
                if (
                    event is not None
                    and isinstance(result, dict)
                    and result.get("success") is False
                ):
                    event.status = "failed"
                    event.data["error_category"] = str(
                        result.get("error_type", "protocol_error")
                    )
                return result

        return StructuredTool.from_function(
            coroutine=_call_tool,
            name=name,
            description=desc or f"Call the {name} MCP tool.",
            args_schema=args_schema,
        )

    @staticmethod
    def _args_schema(name: str, input_schema: Dict[str, Any]) -> Type[BaseModel]:
        """Preserve MCP field names, requiredness and primitive types."""
        properties = input_schema.get("properties", {}) or {}
        required = set(input_schema.get("required", []) or [])
        fields: Dict[str, tuple[Any, Any]] = {}
        for field_name, definition in properties.items():
            definition = definition or {}
            annotation = _JSON_TYPES.get(definition.get("type"), Any)
            default = ... if field_name in required else None
            if default is ...:
                fields[field_name] = (annotation, default)
            else:
                fields[field_name] = (Optional[annotation], default)
        model_name = f"{name.title().replace('_', '')}Input"
        return create_model(model_name, **fields)
