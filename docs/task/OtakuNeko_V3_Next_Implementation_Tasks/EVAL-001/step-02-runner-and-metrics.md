# EVAL-001 Step 02 Runner and Deterministic Metrics

## Files

- Create `backend/app/evaluation/runner.py`.
- Create `backend/app/evaluation/metrics.py`.
- Add a CLI entry in `backend/pyproject.toml` or a module entry point.
- Test in `backend/tests/evaluation/test_runner.py`.

## Requirements

Run cases with injected agents, capabilities, clocks, and providers. Calculate
routing accuracy, schema validity, required/forbidden capability compliance,
factual evidence coverage, error recovery, latency, and call budgets.

## Acceptance

- Deterministic fixtures require no network.
- One case failure does not abort the report.
- Exit code is non-zero when configured required thresholds fail.
