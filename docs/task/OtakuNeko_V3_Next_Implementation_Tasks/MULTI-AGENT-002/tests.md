# MULTI-AGENT-002 Tests

## Required Coverage

- Anime factual, comparison, and partial-provider failures.
- Companion cold memory and established-profile behavior.
- Capability allowlists and denied side effects.
- Anime-to-recommendation and companion-to-anime handoffs.
- Loop, timeout, cancellation, and legacy fallback behavior.
- Golden routing cases consumed by EVAL-001.

## Verification Commands

```bash
cd backend
uv run pytest tests/agents -q
uv run ruff check app/agents tests/agents
uv run pytest tests -q
```
