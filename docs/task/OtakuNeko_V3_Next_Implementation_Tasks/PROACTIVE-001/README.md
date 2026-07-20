# PROACTIVE-001 Scheduled Autonomous Tasks

## Goal

Enable safe, persistent, user-controlled scheduled agent tasks such as seasonal
anime scans, weekly recommendations, and reminders.

## Dependencies

- HARNESS-002
- MEMORY-002
- MULTI-AGENT-001
- EVAL-001
- TRACE-002

## Scope

- Persistent task and run models.
- Scheduler abstraction and a single-process reference implementation.
- AgentRuntime execution with idempotency, retries, timeouts, and leases.
- User APIs to create, pause, resume, inspect, and delete tasks.
- Explicit policy for side effects, notifications, and failure escalation.

## Non-Goals

- Distributed scheduling in the first implementation.
- Agents creating unlimited recurring tasks without user confirmation.
- Silent external side effects.
- Replacing existing schedule-domain records.

## Execution Order

1. Define persistent task/run models and migrations.
2. Implement scheduler and lease semantics.
3. Execute tasks through AgentRuntime and AgentRouter.
4. Add user control and run-history APIs.
5. Add reliability, policy, and restart tests.

## Definition of Done

- Enabled tasks survive restart and execute at most once per scheduled slot.
- Users can pause or delete tasks before the next run.
- Retries are bounded and side effects are idempotent.
- Every run has trace, status, timestamps, and safe error information.
- A scheduler outage does not affect interactive chat.

## Rollback

Disable scheduler startup and stop claiming new work; allow active runs to
finish or expire, retain task/run records for audit, and restore interactive
chat to the pre-scheduler runtime path.

## Related RFC

RFC-106 Scheduler component and success criterion “tasks can run proactively”.
