# MULTI-AGENT-002 Step 02 CompanionAgent

## Files

- Create `backend/app/agents/companion_agent.py`.
- Register the agent.
- Test in `backend/tests/agents/test_companion_agent.py`.

## Requirements

Handle general conversation and use MemoryService for continuity. It may read
profile memory but must use explicit capability actions for external effects.
Define safe fallback when memory is unavailable.

## Acceptance

- General chat routes consistently.
- Memory improves continuity without exposing raw stored records.
- Side effects require a handoff or declared capability action.
