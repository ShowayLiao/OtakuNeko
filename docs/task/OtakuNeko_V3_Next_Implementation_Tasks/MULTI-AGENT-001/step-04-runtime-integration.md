# MULTI-AGENT-001 Step 04 Runtime Integration

## Files

- Modify `backend/app/api/v1/agent.py`.
- Modify or add a Harness routing adapter.
- Add a feature flag in `backend/app/core/config.py`.
- Test in `backend/tests/agents/test_multi_agent_integration.py`.

## Requirements

Keep API -> Harness -> Agent dependency direction. The API must submit one
AgentTask and must not choose a specialist itself. Preserve SSE event schemas,
thread scoping, checkpoints, memory extraction, and provider selection.

## Acceptance

- Feature off is byte-compatible at the SSE contract level.
- Feature on routes recommendations and preserves other chat behavior.
- Cancellation and failures close all adapters and record correct traces.
