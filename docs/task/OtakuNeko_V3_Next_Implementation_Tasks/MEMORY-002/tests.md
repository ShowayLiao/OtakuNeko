# MEMORY-002 Tests

## Required Coverage

- Type validation and serialization.
- Repository CRUD, pagination, and user isolation.
- Alembic upgrade and downgrade.
- Per-kind deduplication and retention.
- Restart persistence using a fresh application/repository instance.
- Anonymous-user behavior and extraction failure fallback.
- Existing chat streaming regression.

## Verification Commands

```bash
cd backend
uv run pytest tests/memory tests/harness/test_api_regression.py -q
uv run ruff check app/memory app/models/agent_memory.py tests/memory
uv run pytest tests -q
```

## Exit Gate

No network-backed embedding call is allowed in unit tests. Integration tests
must use a deterministic fake embedder and a temporary database.
