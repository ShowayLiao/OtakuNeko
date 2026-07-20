# CAPABILITY-002 Step 02 Recommendation Capability

## Files

- Create `backend/app/capabilities/recommendation.py`.
- Adapt existing profile/recommendation service calls.
- Test in `backend/tests/capabilities/test_recommendation.py`.

## Requirements

Expose candidate search, preference-context retrieval, and ranking-input
assembly. Return evidence fields so RecommendationAgent can explain results.
Do not generate conversational prose or invoke an agent from the capability.

## Acceptance

- Empty history has a deterministic fallback.
- Candidate limits and filters are enforced.
- User context is mandatory and isolated.
- Service failures return a typed capability error.
