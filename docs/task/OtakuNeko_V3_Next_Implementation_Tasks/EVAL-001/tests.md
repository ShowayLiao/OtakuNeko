# EVAL-001 Tests

## Required Coverage

- Dataset validation and versioning.
- Every deterministic metric at boundary values.
- Runner isolation and partial failures.
- Judge parsing, timeout, cache, and unavailability.
- Baseline improvement, tolerated drift, and regression.
- CLI exit codes and report schema.

## Verification Commands

```bash
cd backend
uv run pytest tests/evaluation -q
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
uv run ruff check app/evaluation tests/evaluation
uv run pytest tests -q
```
