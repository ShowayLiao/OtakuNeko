# V3-ACCEPTANCE-001 Step 02 End-to-End Scenarios

## Files

- Create `backend/tests/acceptance/`.
- Add deterministic provider, clock, database, and capability fixtures.

## Required Scenarios

1. General chat routes to CompanionAgent and retains memory after restart.
2. Anime comparison routes to AnimeAgent and records evidence-bearing calls.
3. Personalized recommendation uses memory and RecommendationAgent.
4. Cross-domain request performs one controlled handoff.
5. Weekly task survives restart and executes exactly once.
6. Provider failure produces bounded retries and an accurate trace.
7. One user cannot read another user's memory, trace, task, or schedule.

## Acceptance

- Scenarios run without public network access.
- Assertions cover final output, route, capabilities, persistence, and trace.
- Failure output identifies the broken architecture boundary.
