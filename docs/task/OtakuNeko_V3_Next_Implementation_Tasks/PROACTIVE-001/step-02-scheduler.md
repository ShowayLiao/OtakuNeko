# PROACTIVE-001 Step 02 Scheduler and Leases

## Files

- Create modules under `backend/app/harness/scheduler/`.
- Add application startup/shutdown wiring.
- Test in `backend/tests/proactive/test_scheduler.py`.

## Requirements

Poll due tasks with an injected clock, claim them through expiring leases, and
create one run per scheduled slot. Recompute next-run times in the user's
timezone and define daylight-saving behavior. Shutdown must stop claiming work
and allow active work to finish within a bound.

## Acceptance

- Two scheduler instances cannot execute the same slot twice.
- Expired leases are recoverable.
- Restart catches up according to an explicit skip/latest/all policy.
- Interactive API startup can disable the scheduler independently.
