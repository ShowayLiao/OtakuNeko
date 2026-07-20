# MULTI-AGENT-001 Step 03 RecommendationAgent

## Files

- Create `backend/app/agents/recommendation_agent.py`.
- Register it through `backend/app/agents/agent_registry.py`.
- Test in `backend/tests/agents/test_recommendation_agent.py`.

## Requirements

Depend on MemoryService and RecommendationCapability abstractions. Produce a
structured recommendation result containing candidates, evidence, and a user
response. Enforce candidate and model-call budgets.

## Acceptance

- Personalized and cold-start cases are deterministic under test fixtures.
- Capability failure produces an honest fallback response.
- The agent never imports repositories or domain services directly.
