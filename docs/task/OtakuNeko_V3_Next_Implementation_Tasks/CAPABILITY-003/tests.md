# CAPABILITY-003 Tests

## Required Coverage

- Complete legacy-tool parity matrix.
- Capability/action/public-name duplicate detection and stable ordering.
- LangChain schema conversion and input validation.
- Trusted user/dependency injection and model-argument isolation.
- Typed failure semantics and exactly-once tracing.
- Shared production factory inventory.
- Chat local tools, outbound MCP tools, empty tools, and collision behavior.
- MCP exposure allowlist regression.
- Streaming tool events and graph binding parity.
- Architecture bans on `ToolRegistry`, `ALL_TOOLS`, duplicate factories, and
  direct service dependencies.

## Verification Commands

```bash
cd backend
uv run pytest tests/capabilities tests/agents tests/mcp tests/trace -q
uv run pytest tests/architecture -q
uv run ruff check app/capabilities app/agents app/mcp_server tests/capabilities tests/architecture
uv run pytest tests -q
```

## Static Exit Gate

After the legacy-removal step, both commands must return no production
matches:

```bash
rg -n "ToolRegistry|ALL_TOOLS" backend/app
rg -n "CapabilityRegistry\\(" backend/app --glob "*.py"
```

The second command may match only the shared factory implementation. Tests may
construct isolated registries directly.
