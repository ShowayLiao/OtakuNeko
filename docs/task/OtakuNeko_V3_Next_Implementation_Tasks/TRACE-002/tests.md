# TRACE-002 Tests

## Required Coverage

- Event schema and parent-child ordering.
- Recursive redaction and truncation.
- Success, failure, timeout, and stream cancellation.
- Capability and MCP call spans.
- Durable store restart, retention, pagination, and authorization.
- Disabled-tracing behavior and performance budget.

## Verification Commands

```bash
cd backend
uv run pytest tests/trace tests/harness -q
uv run ruff check app/trace app/harness app/agents/langgraph_adapter.py tests/trace
uv run pytest tests -q
```

## Exit Gate

An automated fixture containing representative secrets must prove that none
appear in serialized trace output.
