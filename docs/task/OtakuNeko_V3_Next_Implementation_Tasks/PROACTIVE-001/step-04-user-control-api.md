# PROACTIVE-001 Step 04 User Control and Run History API

## Files

- Create authenticated API routes under `backend/app/api/v1/`.
- Create request/response schemas.
- Add router registration.
- Test authorization and lifecycle behavior.

## Requirements

Provide create, list, pause, resume, update, delete, and run-history endpoints.
The server derives ownership from authentication. Return next-run preview before
creation and require explicit confirmation for recurring side effects.

## Acceptance

- Cross-user access is rejected for tasks and runs.
- Pause prevents future claims without cancelling an unrelated run.
- Delete is idempotent and retains minimal audit history per policy.
