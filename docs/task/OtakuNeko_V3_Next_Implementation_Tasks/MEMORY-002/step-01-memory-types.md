# MEMORY-002 Step 01 Memory Types

## Files

- Create `backend/app/memory/types.py`.
- Extend `backend/app/memory/interfaces.py`.
- Test in `backend/tests/memory/test_types.py`.

## Requirements

Define `MemoryKind` with `episodic`, `semantic`, and `profile`, plus a typed
record carrying id, user_id, optional thread_id, content, importance, source,
timestamps, and metadata. Validate importance in the inclusive range 0..1.

Profile records are user-scoped; episodic records are user and thread scoped;
semantic records are user-scoped and may retain their source thread.

## Acceptance

- Invalid kinds and importance values are rejected.
- Serialization is stable and JSON-compatible.
- No model imports API, agent, or concrete repository modules.

## Rollback

Remove the additive types module; no persistent data exists at this step.
