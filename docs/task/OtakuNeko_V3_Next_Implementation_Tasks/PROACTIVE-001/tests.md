# PROACTIVE-001 Tests

## Required Coverage

- Schedule/timezone validation and DST boundaries.
- Unique scheduled slots, leases, recovery, and concurrent schedulers.
- Restart catch-up policy.
- Runtime success, retry, timeout, cancellation, and idempotent effects.
- API ownership, pause/resume/delete, and run history.
- Trace and evaluation integration.

## Verification Commands

```bash
cd backend
uv run pytest tests/proactive tests/harness -q
uv run ruff check app/harness/scheduler app/api/v1 tests/proactive
uv run pytest tests -q
```

## Exit Gate

All timing tests use an injected clock. No test may depend on wall-clock sleeps
or a live external provider.
