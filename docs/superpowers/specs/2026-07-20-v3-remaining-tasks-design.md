# OtakuNeko V3 Remaining Tasks Design

## Objective

Turn every unfulfilled RFC-101/RFC-106 target into a bounded, independently
verifiable task package under `docs/task/`.

## Decisions

- Preserve completed `*-001` tasks as historical execution baselines.
- Add successor tasks for unfinished work instead of expanding completed scope.
- Expand the existing EVAL-001 and PROACTIVE-001 placeholders in place.
- Require every task to define dependencies, scope, non-goals, steps, tests,
  rollback boundaries, and definition of done.
- Keep database changes additive and require Alembic migrations.

## Task Order

1. MEMORY-002 persistent and typed memory
2. TRACE-002 decision-level observability
3. CAPABILITY-002 remaining domain capabilities
4. MULTI-AGENT-001 router and recommendation agent
5. MULTI-AGENT-002 anime and companion agents
6. EVAL-001 evaluation gates
7. MCP-002 additional capability exposure
8. PROACTIVE-001 scheduled autonomous execution
9. V3-ACCEPTANCE-001 final RFC acceptance

## Completion Rule

RFC-106 is not complete until V3-ACCEPTANCE-001 proves all success criteria
with automated tests and records any intentionally deferred long-term features.
