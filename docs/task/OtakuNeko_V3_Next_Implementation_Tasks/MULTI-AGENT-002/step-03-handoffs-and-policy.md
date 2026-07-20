# MULTI-AGENT-002 Step 03 Handoffs and Capability Policy

## Files

- Modify `backend/app/agents/router.py` and routing contracts.
- Create `backend/app/agents/policy.py`.
- Test in `backend/tests/agents/test_handoffs.py`.

## Requirements

Define per-agent capability allowlists, handoff reasons, budgets, and terminal
fallbacks. A handoff carries a bounded summary and references to shared state,
not duplicated private memory or full internal prompts.

## Acceptance

- Unauthorized capability calls are rejected before execution.
- Handoff loops terminate predictably.
- A failed specialist returns control to the router once, then falls back.
