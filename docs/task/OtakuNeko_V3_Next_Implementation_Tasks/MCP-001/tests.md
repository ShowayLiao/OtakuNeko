# MCP-001 Tests

## Required Coverage

- Anime tool names and schemas are generated from action descriptors.
- The registry exposed by the entry point contains only AnimeCapability.
- initialize, tools/list, tools/call, and unknown-method behavior.
- Unknown tool handling.
- Fail-closed behavior for authenticated and side-effecting actions.
- Existing backend behavior remains unchanged.

## Verification Commands

```bash
cd backend
uv run pytest tests/mcp -q
uv run ruff check app/mcp_server tests/mcp
uv run pytest tests -q
```

MCP-002 adds real subprocess stdio, malformed-frame, cancellation, size-limit,
and authenticated policy coverage.
