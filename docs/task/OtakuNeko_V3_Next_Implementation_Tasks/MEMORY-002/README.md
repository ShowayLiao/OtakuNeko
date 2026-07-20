# MEMORY-002 Persistent and Typed Memory

## Goal

Finish RFC-101 Phase 4 by making memory durable and separating episodic,
semantic, and profile records behind the existing MemoryService boundary.

## Background

MEMORY-001 introduced service, repository, extractor, and hybrid retrieval
interfaces. The current API still constructs an in-memory repository, so facts
do not survive process restarts and all memory records share one shape.

## Dependencies

- MEMORY-001
- HARNESS-002
- Existing Alembic infrastructure

## Scope

- Add typed memory records and ownership rules.
- Add SQL-backed repository and additive migrations.
- Preserve the current MemoryService interface where possible.
- Migrate chat runtime wiring from InMemoryStore to durable storage.
- Provide retention, deduplication, deletion, and user isolation.

## Non-Goals

- Graph database adoption.
- Cross-user recommendations.
- Replacing LangGraph checkpoints.
- Automatic profile editing UI.

## Execution Order

1. Define typed memory records.
2. Add database schema and SQL repository.
3. Update service retrieval and retention behavior.
4. Wire durable memory into the chat API.
5. Add migration, isolation, and restart tests.

## Definition of Done

- Memory survives application restart.
- Episodic, semantic, and profile records can be stored and retrieved.
- Every query is scoped to the authenticated user and thread as appropriate.
- Existing chat and MEMORY-001 tests remain green.
- Alembic upgrade and downgrade are verified.

## Rollback

Disable durable-memory wiring and restore the MEMORY-001 repository binding;
retain the additive migration until its data-retention and downgrade drill is
complete.

## Related RFC

RFC-101 Phase 4, RFC-104, RFC-106 Principles 1 and 2.
