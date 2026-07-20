# MULTI-AGENT-002 Anime and Companion Agents

## Goal

Complete the initial specialist split with AnimeAgent and CompanionAgent, using
the router and handoff contracts proven in MULTI-AGENT-001.

## Dependencies

- MULTI-AGENT-001
- CAPABILITY-002

## Scope

- AnimeAgent for factual anime knowledge and comparison.
- CompanionAgent for general conversation and relationship continuity.
- Explicit specialist-to-specialist handoffs.
- Per-agent prompts, capability allowlists, budgets, and evaluation cases.

## Non-Goals

- New capability providers.
- Background scheduling.
- Unlimited recursive collaboration.

## Execution Order

1. Implement AnimeAgent.
2. Implement CompanionAgent.
3. Add controlled handoffs and capability policies.
4. Complete routing and regression suites.

## Definition of Done

- All three initial specialists are registered and routable.
- Each agent accesses only its declared capabilities.
- Cross-domain requests hand off at most the configured number of times.
- Existing general chat behavior remains available through CompanionAgent or
  the legacy fallback during rollout.

## Rollback

Disable specialist registrations and route all requests through
MULTI-AGENT-001's router fallback; preserve shared routing contracts and avoid
removing capability policy data needed by existing agents.

## Related RFC

RFC-101 Phase 5 and RFC-106 success criterion “multiple agents cooperate”.
