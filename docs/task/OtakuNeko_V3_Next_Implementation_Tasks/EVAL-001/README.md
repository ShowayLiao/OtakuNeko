# EVAL-001 Agent Evaluation Framework

## Goal

Create a reproducible evaluation loop that blocks regressions in routing,
factuality, recommendation quality, safety, and latency.

## Dependencies

- TRACE-002
- MULTI-AGENT-001
- RFC-104

## Scope

- Versioned offline datasets and golden cases.
- Deterministic metrics for routing, schemas, citations, and budgets.
- Optional model judge behind a stable interface.
- Baseline comparison and CI reporting.
- Separate fast PR gates from scheduled full evaluations.

## Non-Goals

- Training or fine-tuning models.
- Treating an LLM judge as the only correctness signal.
- Running paid evaluation calls in every unit-test invocation.

## Execution Order

1. Define dataset format and initial golden cases.
2. Implement deterministic metrics and runner.
3. Add calibrated judge interface.
4. Store baselines and compare regressions.
5. Integrate fast and scheduled CI gates.

## Definition of Done

- The same dataset and configuration produce reproducible reports.
- Required routing and safety thresholds fail CI when violated.
- Judge failures are reported as unavailable, never silently treated as pass.
- Reports identify task, agent, model configuration, and code revision.

## Rollback

Disable the new CI evaluation gates and retain the last approved deterministic
baseline; do not overwrite published datasets, baselines, or threshold
configuration during rollback.

## Related RFC

RFC-104 Sections 6-10 and RFC-106 Harness Evaluation component.
