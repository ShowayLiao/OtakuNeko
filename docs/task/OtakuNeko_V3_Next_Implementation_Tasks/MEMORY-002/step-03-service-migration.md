# MEMORY-002 Step 03 Service Migration

## Files

- Modify `backend/app/memory/service.py`.
- Modify `backend/app/memory/extractor.py`.
- Modify `backend/app/api/v1/agent.py`.
- Test in `backend/tests/memory/test_service_typed.py` and
  `backend/tests/harness/test_api_regression.py`.

## Requirements

Extend store and search operations with user_id and memory kind while retaining
a compatibility path for current callers during this task. Deduplication must
occur within the same user and kind. Retention limits must never delete profile
memory merely because episodic memory reached its limit.

Construct the SQL repository through FastAPI dependencies. Do not cache live
database sessions globally. Extraction failure must not fail a completed chat.

## Acceptance

- New chats write durable semantic facts for authenticated users.
- Anonymous chats do not create durable user memory.
- Retrieval combines relevant typed memory without crossing user boundaries.
- Provider and extraction failures have deterministic fallback behavior.

## Rollback

Switch dependency wiring back to StoreMemoryRepository without reverting the
additive database migration.
