# FRONTEND-AI-001 Step 01 Typed API Contracts

## Files

- Create `frontend/src/types/ai.ts`.
- Create `frontend/src/services/ai.ts`.
- Create `frontend/src/services/ai.test.ts`.
- Reuse `frontend/src/services/client.ts`.

## Requirements

Define frontend types that match the existing response shapes from
`/api/v1/trace`, `/api/v1/proactive`, and `/api/v1/memory`. Keep serialized
task `payload` and `policy` fields explicit: parse them through safe helpers
that preserve the original value and surface invalid JSON instead of silently
substituting `{}`.

Expose focused service functions for:

- trace list/detail with `limit`, `cursor`, `task_id`, `status`,
  `started_after`, and `started_before`;
- proactive task list/create/update/preview/pause/resume/delete/run history;
- memory deletion with optional `episodic`, `semantic`, or `profile` kind.

All calls must use the authenticated request path in `services/client.ts`.
Clients must not accept a `user_id` capable of widening backend ownership.
Handle `204 No Content` in the shared client or the delete function without
attempting JSON decoding.

## Acceptance

- Types preserve trace event ordering, timestamps, status, and correlation ids.
- Query serialization omits unset filters and URL-encodes all values.
- `401`, `404`, `422`, network failure, malformed task JSON, and `204` delete
  responses have deterministic tests.
- No provider key, endpoint, bearer token, or raw private prompt is included in
  an AI workspace URL or persisted view state.
