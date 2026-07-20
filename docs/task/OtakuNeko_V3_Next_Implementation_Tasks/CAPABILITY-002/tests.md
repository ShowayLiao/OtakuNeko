# CAPABILITY-002 Tests

## Required Coverage

- Action metadata, discovery, and duplicate detection.
- Typed success and error results.
- Recommendation fallback and evidence.
- Schedule authorization, validation, and idempotency.
- Media not-configured behavior.
- Tool schema and behavior regressions.
- Architecture dependency test.

## Verification Commands

```bash
cd backend
uv run pytest tests/capabilities tests/agents/tools -q
uv run ruff check app/capabilities app/agents/tools tests/capabilities
uv run pytest tests -q
```
