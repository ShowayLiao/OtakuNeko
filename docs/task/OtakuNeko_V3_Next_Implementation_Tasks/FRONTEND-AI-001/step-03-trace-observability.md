# FRONTEND-AI-001 Step 03 Trace Observability

## Files

- Create `frontend/src/components/ai/trace/TraceExplorer.tsx`.
- Create `frontend/src/components/ai/trace/TraceFilters.tsx`.
- Create `frontend/src/components/ai/trace/TraceList.tsx`.
- Create `frontend/src/components/ai/trace/TraceDetail.tsx`.
- Create `frontend/src/components/ai/trace/TraceEventTimeline.tsx`.
- Test components under `frontend/src/components/ai/trace/`.

## Requirements

Build a trace explorer over the authenticated `/api/v1/trace` API. Support
status, task, and start-time filters plus backend cursor pagination. Reset the
cursor when a filter changes and prevent stale or aborted responses from
overwriting the latest query.

The detail view must render structured trace metadata and events in recorded
order. Reuse the status language and visual rhythm of
`AgentMessageRenderer`/`ProcessStepItem`, but keep trace components independent
of the live chat Zustand store.

Render bounded, redacted event data as readable JSON. Never label data as
hidden reasoning, attempt to reconstruct chain-of-thought, or expose values
that the API has redacted. Provide copy actions only for safe identifiers such
as trace id and task id.

## Acceptance

- Empty, loading, failed, cancelled, completed, and not-found traces have
  distinct states.
- Cursor pagination appends exactly once and cannot mix different filter sets.
- Selecting a trace does not trigger a cross-user fallback when the API returns
  `404`.
- Timeline order, duration display, redacted payload display, stale-response
  protection, and retry behavior have deterministic tests.
