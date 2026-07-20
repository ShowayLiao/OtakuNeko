# MEMORY-002 Step 04 Retention and Deletion

## Files

- Modify `backend/app/memory/service.py`.
- Add authenticated memory deletion endpoints under `backend/app/api/v1/`.
- Test in `backend/tests/memory/test_retention.py` and API tests.

## Requirements

Define per-kind retention limits, deterministic eviction by importance and age,
and explicit user deletion. Deleting a user's memory must be auditable and must
not delete chat messages or another user's records.

## Acceptance

- Capacity is enforced after every insert.
- Explicit deletion is idempotent.
- Profile memory requires explicit replacement or deletion.
- Logs contain ids and counts but not raw private memory content.
