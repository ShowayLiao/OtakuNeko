# FRONTEND-AI-001 Step 04 Proactive Task Management

## Files

- Create `frontend/src/components/ai/proactive/ProactiveTaskPanel.tsx`.
- Create `frontend/src/components/ai/proactive/TaskList.tsx`.
- Create `frontend/src/components/ai/proactive/TaskEditor.tsx`.
- Create `frontend/src/components/ai/proactive/SchedulePreview.tsx`.
- Create `frontend/src/components/ai/proactive/TaskRunHistory.tsx`.
- Test components under `frontend/src/components/ai/proactive/`.

## Requirements

Implement user controls matching the existing proactive API: list, create,
update, schedule preview, pause, resume, delete, and run history. The editor
must treat `schedule_expr`, IANA timezone, catch-up policy, payload, policy, and
side-effect confirmation as separate fields.

Schedule preview must be debounced or explicitly requested, ignore stale
responses, and display the returned instant in both the task timezone and the
user's local timezone. Invalid cron/timezone responses must stay attached to
the relevant field.

Pause/resume operations must be idempotent from the user's perspective. Delete
requires a task-specific confirmation. A policy marked as requiring a side
effect must require an unchecked-by-default confirmation for each create or
relevant update request.

This UI is separate from `SmartSubscriptionModal`, whose RSS/qBittorrent data
contract and side effects are unrelated.

## Acceptance

- The UI never reports a task mutation as successful before the server
  responds.
- Mutation buttons cannot issue duplicate concurrent requests.
- Run history distinguishes scheduled slot, start/end time, status, retry, and
  safe failure information when present.
- `401`, `404`, `422`, scheduler-unavailable, stale preview, and mutation retry
  states have tests.
