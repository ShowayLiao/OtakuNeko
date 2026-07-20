# MCP-002 Tests

## Required Coverage

- Dynamic discovery and schema validation.
- Anime compatibility.
- Authenticated reads and protected writes.
- Cross-user denial and idempotency.
- JSON-RPC errors, malformed input, cancellation, EOF, and size limits.
- Subprocess stdio end-to-end test.

## Verification Commands

```bash
cd backend
uv run pytest tests/mcp tests/agents/mcp -q
uv run ruff check app/mcp_server app/agents/mcp tests/mcp
uv run pytest tests -q
```
