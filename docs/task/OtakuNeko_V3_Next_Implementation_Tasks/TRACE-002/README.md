# TRACE-002 Decision-Level Observability

## Goal

Extend TRACE-001 from lifecycle traces to useful, privacy-safe records of agent
nodes, decisions, capability calls, MCP calls, timing, and failures.

## Dependencies

- TRACE-001
- HARNESS-001
- CAPABILITY-001

## Scope

- Add structured trace events and correlation ids.
- Instrument LangGraph adapter, capabilities, and MCP boundaries.
- Redact secrets and limit payload sizes before persistence.
- Add durable trace storage with retention.
- Preserve streaming latency and failure semantics.

## Non-Goals

- Storing hidden chain-of-thought.
- Full distributed tracing platform adoption.
- Frontend trace visualization.

## Execution Order

1. Define event taxonomy and redaction policy.
2. Add runtime and adapter instrumentation.
3. Add capability and MCP spans.
4. Add durable storage and query filters.
5. Verify overhead, privacy, and failures.

## Definition of Done

- A chat trace identifies agent nodes and external calls in order.
- Failed operations remain failed and include a safe error category.
- API keys, authorization headers, prompts marked private, and raw memory are
  never stored.
- Trace overhead is measured and bounded.

## Rollback

Disable decision-level instrumentation and restore TRACE-001 lifecycle
recording; keep the additive trace migration reversible and preserve existing
chat behavior.

## Related RFC

RFC-106 Principle 4, TRACE-001, RFC-104.
