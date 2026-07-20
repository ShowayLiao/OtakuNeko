# MULTI-AGENT-001 Router and Recommendation Agent

## Goal

Begin RFC-101 Phase 5 with one bounded specialist and a deterministic router,
while retaining the current LangGraph adapter as the fallback agent.

## Dependencies

- AGENT-001
- MEMORY-002
- CAPABILITY-002
- TRACE-002

## Scope

- Define routed-agent request and handoff contracts.
- Implement AgentRouter with explicit fallback.
- Implement RecommendationAgent using RecommendationCapability.
- Integrate routing behind a feature flag at the Harness boundary.
- Trace routing decisions without storing hidden reasoning.

## Non-Goals

- AnimeAgent and CompanionAgent.
- Autonomous background execution.
- LLM-only routing with no deterministic fallback.
- Rewriting the existing ChatWorkflow graph.

## Execution Order

1. Define routing and handoff contracts.
2. Implement deterministic routing policy.
3. Implement RecommendationAgent.
4. Integrate through AgentRuntime and feature flag.
5. Add evaluation-ready routing fixtures.

## Definition of Done

- Recommendation requests reach RecommendationAgent.
- Unsupported or ambiguous requests safely reach the legacy adapter.
- Route loops and repeated handoffs are bounded.
- Disabling the flag restores current behavior without code changes.

## Rollback

Turn off the routing feature flag and restore the legacy adapter as the sole
runtime path; retain routing contracts and traces as inactive compatibility
code until dependent evaluations are removed.

## Related RFC

RFC-101 Phase 5, RFC-106 Agent Layer.
