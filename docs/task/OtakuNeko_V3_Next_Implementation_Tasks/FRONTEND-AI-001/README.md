# FRONTEND-AI-001 User AI Workspace

## Goal

Add a user-scoped AI management and observability workspace to the existing
Next.js frontend by building on the current chat, provider configuration,
authentication, and Lobe UI layout.

## Dependencies

- MEMORY-002
- TRACE-002
- PROACTIVE-001
- Existing frontend chat and provider configuration

## Scope

- A dedicated `/ai` workspace linked from the existing desktop side navigation.
- Typed frontend clients for trace, proactive-task, and memory APIs.
- Trace list, filtering, cursor pagination, and structured event details.
- Proactive-task creation, schedule preview, pause, resume, edit, delete, and
  run-history views.
- Reuse of the existing provider/API-key settings without moving secrets to
  backend persistence.
- Explicit, confirmed deletion controls for the authenticated user's memory.
- Responsive, accessible loading, empty, unavailable, error, and destructive
  action states.

## Non-Goals

- Displaying or storing hidden chain-of-thought.
- Browsing memory records when the backend only exposes deletion.
- Changing deployment feature flags or adding an administrator role model.
- Treating the RSS/qBittorrent smart-subscription modal as a proactive-agent
  task editor.
- Replacing the existing chat page, session store, or streaming renderer.

## Existing Frontend Integration Points

- `frontend/src/app/APPLayout.tsx` owns full-screen page behavior.
- `frontend/src/features/Sidebar/index.tsx` owns primary navigation.
- `frontend/src/services/client.ts` supplies authenticated JSON requests.
- `frontend/src/lib/fetcher.ts` remains responsible for chat streaming.
- `frontend/src/components/Modal/ApiKeyModal.tsx` and
  `frontend/src/store/useApiStore.ts` own provider secrets and settings.
- `frontend/src/components/chat/AgentMessageRenderer.tsx` is the visual
  reference for structured agent execution states.

## Execution Order

1. Define typed AI API contracts and service clients.
2. Add the AI workspace shell and navigation.
3. Implement trace observability.
4. Implement proactive-task management.
5. Integrate provider and memory controls, then harden the full workspace.

## Definition of Done

- An authenticated user can open `/ai` and inspect only their own traces and
  proactive tasks.
- Trace filters and cursor pagination use the backend contract without
  client-side ownership overrides.
- Task mutations require clear feedback; side-effect and delete operations
  require explicit confirmation.
- Provider API keys remain local to the existing provider store and are never
  rendered in trace or task details.
- Memory controls describe their destructive scope and report the backend
  deletion count.
- Frontend unit tests, type checking, lint, and production build pass.

## Rollback

Remove the `/ai` navigation entry and route, then remove the additive AI service
and component modules. Existing chat, provider settings, backend APIs, and user
data remain unchanged.

## Related Tasks

MEMORY-002, TRACE-002, PROACTIVE-001.
