# V3-ACCEPTANCE-001 Tests

## Required Gates

- Architecture dependency tests.
- Unit, integration, regression, and acceptance suites.
- Alembic upgrade/downgrade drills.
- Fast deterministic evaluation thresholds.
- Security isolation across memory, traces, tasks, schedules, and MCP.
- Interactive streaming and proactive execution performance budgets.

## Verification Commands

```bash
cd backend
uv run pytest tests/architecture tests/acceptance -q
uv run pytest tests -q
uv run ruff check app tests
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
```

Repository-specific frontend checks and migration drills must be appended to the
final completion report with their exact commands and outputs.

## Exit Gate

Do not mark RFC-106 complete if any success-criteria evidence is missing,
skipped, flaky, or depends on an undocumented manual assumption.
