# MULTI-AGENT-001 Step 01 Routing Contract

## Files

- Create `backend/app/agents/routing.py`.
- Extend `backend/app/agents/base.py` only if required.
- Test in `backend/tests/agents/test_routing_contract.py`.

## Requirements

Define route intent, confidence, selected agent, safe rationale summary, and
handoff metadata. Include maximum handoff count and visited-agent tracking.
Contracts must remain independent of LangGraph message classes.

## Acceptance

- Contracts serialize through AgentState context.
- Invalid or cyclic handoffs are rejected.
- No raw chain-of-thought field exists.
