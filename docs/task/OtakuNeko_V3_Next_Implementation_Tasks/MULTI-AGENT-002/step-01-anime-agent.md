# MULTI-AGENT-002 Step 01 AnimeAgent

## Files

- Create `backend/app/agents/anime_agent.py`.
- Register the agent.
- Test in `backend/tests/agents/test_anime_agent.py`.

## Requirements

Use AnimeCapability for facts, staff, cast, reviews, and search. Require source
evidence for factual claims and distinguish missing data from provider failure.
Do not import Bangumi services or tools directly.

## Acceptance

- Search, detail, comparison, and unavailable-data cases pass.
- Capability allowlist excludes schedule writes and profile mutation.
- Outputs remain useful when one optional data call fails.
