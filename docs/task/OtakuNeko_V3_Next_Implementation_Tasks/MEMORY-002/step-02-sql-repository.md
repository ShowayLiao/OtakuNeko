# MEMORY-002 Step 02 SQL Repository

## Files

- Create `backend/app/models/agent_memory.py`.
- Create `backend/app/memory/sql_repository.py`.
- Modify `backend/app/models/__init__.py`.
- Create an Alembic revision under `backend/alembic/versions/`.
- Test in `backend/tests/memory/test_sql_repository.py`.

## Requirements

Create an additive `agent_memory` table with indexed user, thread, kind, and
created-at columns. The repository must implement the MemoryRepository contract
without leaking SQLAlchemy sessions into MemoryService.

All read, update, and delete operations must require user ownership. Pagination
must have a deterministic order. Deletion must be idempotent.

## Acceptance

- Upgrade creates the table and downgrade removes only this table.
- Two users with the same thread id cannot read each other's memory.
- Repository contract tests run against SQLite and the production SQL dialect
  remains supported by the migration.

## Rollback

Downgrade the single migration and restore the prior repository binding.
