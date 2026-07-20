# MULTI-AGENT-001 Step 02 AgentRouter

## Files

- Create `backend/app/agents/router.py`.
- Modify `backend/app/agents/agent_registry.py`.
- Test in `backend/tests/agents/test_agent_router.py`.

## Requirements

Route explicit recommendation intents deterministically first. An optional model
classifier may handle ambiguous queries, but timeout, invalid output, or low
confidence must select the legacy adapter. Never execute side effects in routing.

## Acceptance

- Known intents route without a model call.
- Unknown input falls back safely.
- Missing registered agents produce a controlled error or fallback.
- Routing is traceable and bounded.
