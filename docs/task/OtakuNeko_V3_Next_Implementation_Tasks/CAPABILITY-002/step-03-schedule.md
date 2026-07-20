# CAPABILITY-002 Step 03 Schedule Capability

## Files

- Create `backend/app/capabilities/schedule.py`.
- Reuse `backend/app/services/schedule_service.py`.
- Migrate schedule-related agent tools if present.
- Test in `backend/tests/capabilities/test_schedule.py`.

## Requirements

Expose list, create/update, and delete actions using the existing schedule
schemas. Write actions must declare side effects, validate ownership, and use
idempotency keys where duplicate execution could create duplicate schedules.

## Acceptance

- Cross-user access is rejected.
- Replaying an idempotent request does not duplicate data.
- Existing REST schedule endpoints retain behavior.
