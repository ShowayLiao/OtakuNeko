# EVAL-001 Step 04 CI Gates

## Files

- Add or modify repository CI workflow files.
- Create `backend/evals/config/fast.yaml` and `full.yaml`.
- Document local execution.

## Requirements

PR checks run deterministic fast cases. Scheduled/manual workflows may run
network-backed judge cases with protected secrets, concurrency limits, and cost
budgets. Upload machine-readable and human-readable reports.

## Acceptance

- Fast evaluation is mandatory and does not require secrets.
- Full evaluation cannot expose provider responses containing secrets.
- Threshold changes require a reviewed config diff.
