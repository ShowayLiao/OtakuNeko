import pytest

from app.agents.tools.base import log_tool_call


@pytest.mark.asyncio
async def test_tool_decorator_adds_stable_result_metadata():
    @log_tool_call("example")
    async def example(value: int):
        return {"value": value}

    result = await example(3)

    assert result["success"] is True
    assert result["tool_name"] == "example"
    assert result["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_tool_decorator_returns_structured_error():
    @log_tool_call("broken")
    async def broken():
        raise RuntimeError("boom")

    result = await broken()

    assert result["success"] is False
    assert result["error_type"] == "internal"
    assert result["tool_name"] == "broken"
