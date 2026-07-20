# EVAL-001 Step 01 Dataset and Golden Cases

## Files

- Create `backend/evals/datasets/` with versioned JSONL fixtures.
- Create `backend/app/evaluation/types.py`.
- Test in `backend/tests/evaluation/test_dataset.py`.

## Requirements

Each case defines id, category, input messages, user/memory fixtures, expected
route, required/forbidden capabilities, assertions, and tags. Start with anime
knowledge, recommendation, companion, ambiguous routing, prompt injection,
provider failure, and cancellation cases.

## Acceptance

- Duplicate ids and unknown fields fail validation.
- Dataset versions are explicit and immutable after baseline publication.
- Fixtures contain no real credentials or personal data.
