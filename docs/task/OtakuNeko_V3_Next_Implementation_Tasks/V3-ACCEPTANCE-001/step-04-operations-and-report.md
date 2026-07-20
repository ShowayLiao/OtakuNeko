# V3-ACCEPTANCE-001 Step 04 Operations and Completion Report

## Files

- Update deployment and rollback documentation.
- Create the final RFC-106 completion report under `docs/reports/`.

## Requirements

Document migrations, scheduler enablement, trace/memory retention, provider
configuration, evaluation commands, incident diagnosis, and rollback order.
Run upgrade and downgrade drills against disposable environments.

The report must include code revision, commands, pass/fail counts, performance
budgets, known limitations, and explicitly deferred long-term capabilities.

## Acceptance

- A new operator can start, validate, and roll back V3 from documentation.
- Rollback does not destroy existing V2 user/anime data.
- Completion is declared only when all required evidence is green.
