# EVAL-001 Step 03 Judge and Baseline Comparison

## Files

- Create `backend/app/evaluation/judge.py`.
- Create `backend/evals/baselines/`.
- Test in `backend/tests/evaluation/test_judge.py`.

## Requirements

Define a judge interface returning score, rubric dimensions, and explanation.
Calibrate it against human-authored fixtures. Cache judge inputs by content hash
and record model/provider configuration. Compare current metrics with an
explicit baseline and tolerance per metric.

## Acceptance

- Judge disagreement and unavailability remain visible.
- No baseline is overwritten implicitly.
- Deterministic safety assertions override judge scores.
