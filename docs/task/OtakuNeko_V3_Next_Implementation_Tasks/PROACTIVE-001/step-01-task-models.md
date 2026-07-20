# PROACTIVE-001 Step 01 Persistent Task and Run Models

## Files

- Create `backend/app/models/agent_task.py` and `agent_task_run.py`.
- Create repository interfaces under `backend/app/harness/scheduler/`.
- Add an Alembic revision.
- Test model and repository behavior.

## Requirements

Store owner, task type, validated payload, schedule expression, timezone,
enabled state, next run, idempotency key, policy, and timestamps. Runs store
scheduled slot, attempt, lease, status, trace id, and safe error category.

## Acceptance

- Unique owner/task/slot constraints prevent duplicate runs.
- Invalid timezone and schedules are rejected.
- Migration is additive and reversible.
- Payloads cannot contain provider credentials.
