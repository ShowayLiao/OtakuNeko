import time
import functools
from typing import Any, Optional, Literal
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


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
                success = result.get("success", True) if isinstance(result, dict) else True
                logger.info("tool_called", extra={
                    "tool_name": tool_name,
                    "tool_args": str(kwargs)[:200],
                    "duration_ms": round(duration_ms, 2),
                    "success": success,
                })
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000
                logger.error("tool_failed", extra={
                    "tool_name": tool_name,
                    "tool_args": str(kwargs)[:200],
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                })
                return {"error": str(e)}
        return wrapper
    return decorator
