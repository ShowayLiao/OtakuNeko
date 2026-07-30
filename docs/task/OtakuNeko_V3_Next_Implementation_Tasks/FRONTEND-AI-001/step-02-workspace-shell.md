# FRONTEND-AI-001 Step 02 Workspace Shell and Navigation

## Files

- Create `frontend/src/app/ai/page.tsx`.
- Create `frontend/src/components/ai/AIWorkspace.tsx`.
- Create `frontend/src/components/ai/AIWorkspaceHeader.tsx`.
- Create `frontend/src/components/ai/AIWorkspaceNav.tsx`.
- Modify `frontend/src/features/Sidebar/index.tsx`.
- Modify `frontend/src/app/APPLayout.tsx`.
- Test `frontend/src/components/ai/AIWorkspace.test.tsx`.

## Requirements

Add an AI workspace entry to the existing Lobe UI `SideNav`; do not create a
second application shell. The active state must derive from `usePathname` so a
direct navigation or browser history change cannot leave the wrong icon active.

Use a full-height workspace consistent with chat, collections, timetable, and
personal pages. Update `APPLayout` with an explicit `/ai` full-screen route
instead of a broad substring match.

Provide stable sections for:

- Observability;
- Scheduled tasks;
- Models and memory.

The selected section may be represented by a validated URL query parameter so
refresh and deep links are stable. Invalid values must fall back to
observability. Each section must own its loading and error boundary so one
failed API does not blank the whole workspace.

## Acceptance

- `/ai` is reachable from the sidebar and has correct active state after direct
  load, client navigation, and history navigation.
- The workspace fits the existing fixed layout without nested viewport scroll
  traps.
- Keyboard navigation, visible focus, section labels, and narrow-screen layout
  are covered by component tests.
- The unused `/settings` route is not repurposed or expanded by this task.
