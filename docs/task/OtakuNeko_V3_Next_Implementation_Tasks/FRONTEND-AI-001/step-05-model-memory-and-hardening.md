# FRONTEND-AI-001 Step 05 Model, Memory, and Workspace Hardening

## Files

- Refactor `frontend/src/components/Modal/ApiKeyModal.tsx`.
- Create `frontend/src/components/ai/settings/ProviderSettingsPanel.tsx`.
- Create `frontend/src/components/ai/settings/MemoryControls.tsx`.
- Reuse `frontend/src/store/useApiStore.ts`.
- Test components under `frontend/src/components/ai/settings/`.
- Modify `frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx`
  only if shared presentation behavior changes.

## Requirements

Extract a provider-settings panel that can be used by both the existing modal
and the AI workspace. Preserve provider enablement, endpoint, DeepSeek
thinking options, model validation, and local persistence behavior. Do not
render a saved API key as plain text or send it to any trace, proactive, or
memory endpoint.

Add memory deletion controls for one memory kind or all memory. Explain that
the backend exposes deletion rather than browsing, require a typed or
equivalent high-intent confirmation for deleting all memory, and show the
returned deletion count. Clear local success state when the selected scope
changes.

Complete responsive behavior, focus restoration after dialogs, reduced-motion
support for timelines, request cancellation on unmount, and consistent
notifications. Avoid a new global store unless state must survive navigation;
server data should remain component/query state rather than enter
`useChatStore`.

## Acceptance

- The chat page can still open and use provider settings after extraction.
- Provider validation keeps the existing `/api/v1/models/check` behavior.
- Cancelling a memory confirmation issues no request.
- Successful partial and full deletion, zero deleted rows, authorization
  failure, and retry are tested.
- Workspace components do not log secrets or persist trace/task response data
  to localStorage.
