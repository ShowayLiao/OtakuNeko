# MULTI-AGENT-001 Tests

## Required Coverage

- Deterministic, ambiguous, low-confidence, and missing-agent routes.
- Handoff limit and cycle prevention.
- Recommendation cold-start, personalized, and failure paths.
- Feature-flag on/off API regression.
- Memory and trace integration.
- Dependency direction checks.

## Verification Commands

```bash
cd backend
uv run pytest tests/agents tests/harness -q
uv run ruff check app/agents app/harness tests/agents
uv run pytest tests -q
```
