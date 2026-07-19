# HARNESS-001 Introduce AgentRuntime

## Goal

Introduce the first Harness abstraction layer without changing existing
behavior.

## Execution Order

1.  Create task model
2.  Create runtime state
3.  Create runtime executor
4.  Wrap existing ChatWorkflow
5.  Switch API entrypoint
6.  Add tests

## Related RFC

RFC-003 RFC-101 RFC-102
