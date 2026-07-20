# TRACE-002 Step 04 Durable Trace Store

## Files

- Create `backend/app/models/agent_trace.py`.
- Add a SQL TraceStore implementation under `backend/app/trace/`.
- Create an additive Alembic revision.
- Modify `backend/app/api/v1/trace.py`.
- Test repository and authorization behavior.

## Requirements

Persist trace headers and structured events with indexed user, task, status,
and start-time fields. Query endpoints must always enforce current-user scope.
Apply age/count retention without blocking request streaming.

## Acceptance

- Traces survive restart and remain user-isolated.
- Pagination is stable and bounded.
- A storage failure is logged but does not replace the agent result.
