import time
import functools
import json
from typing import Any, Optional, Literal
from pydantic import BaseModel

from app.core.logging import get_logger
from app.trace.redaction import redact

logger = get_logger(__name__)


def _safe_tool_result(result: Any, tool_name: str, duration_ms: float) -> dict[str, Any]:
    """Return a bounded, redacted result for ToolNode and downstream adapters."""
    if isinstance(result, dict):
        safe_result = redact(result)
    else:
        safe_result = {"data": redact(result)}
    if not isinstance(safe_result, dict):
        safe_result = {"data": safe_result}
    try:
        json.dumps(safe_result, ensure_ascii=False)
    except (TypeError, ValueError):
        safe_result = {
            "success": False,
            "data": {},
            "error": "Tool output was not serializable",
            "error_type": "invalid_output",
        }
    success = bool(safe_result.get("success", True))
    safe_result.setdefault("success", success)
    safe_result.setdefault("tool_name", tool_name)
    safe_result.setdefault("duration_ms", round(duration_ms, 2))
    if not success:
        safe_result.setdefault("error_type", "internal")
        safe_result["error"] = "Tool execution failed"
    return safe_result


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Optional[Literal["network", "not_found", "invalid_args", "internal"]] = None
    tool_name: str
    duration_ms: float


def log_tool_call(tool_name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - t0) * 1000
                safe_result = _safe_tool_result(result, tool_name, duration_ms)
                success = safe_result["success"]
                logger.info("tool_called", extra={
                    "tool_name": tool_name,
                    "argument_shape": {
                        "count": len(kwargs),
                        "types": sorted(
                            type(value).__name__ for value in kwargs.values()
                        ),
                    },
                    "duration_ms": round(duration_ms, 2),
                    "success": success,
                })
                return safe_result
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                logger.error("tool_failed", extra={
                    "tool_name": tool_name,
                    "argument_shape": {
                        "count": len(kwargs),
                        "types": sorted(
                            type(value).__name__ for value in kwargs.values()
                        ),
                    },
                    "duration_ms": round(duration_ms, 2),
                    "error_category": type(exc).__name__,
                })
                return {
                    "success": False,
                    "error": "Tool execution failed",
                    "error_type": "internal",
                    "tool_name": tool_name,
                    "duration_ms": round(duration_ms, 2),
                }
        return wrapper
    return decorator
