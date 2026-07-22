# MCP-001 Step 03 Pilot Protocol and Security Boundary

## Files

- Modify `backend/app/mcp_server/__init__.py`.
- Test in `backend/tests/mcp/test_server.py`.

## Requirements

Support the minimum pilot request flow: initialize, initialized notification,
tools/list, and tools/call. Return a JSON-RPC method-not-found error for unknown
methods and serialize capability results as MCP text content without discarding
their success or typed error fields.

The generic dispatcher may be constructed with other registries in tests, but
it must fail closed when an action requires authentication or has side effects.
Tool arguments are untrusted input and must never be treated as authentication
or policy approval.

## Acceptance

- The initialize/list/call flow remains compatible with the Anime pilot.
- Unknown methods use JSON-RPC error code `-32601`.
- Unknown tools return a structured capability-style failure.
- Actions marked `requires_auth` are denied without trusted context.
- Actions marked `is_side_effect` are denied without explicit policy support.
- Malformed frames, cancellation, response limits, subprocess conformance, and
  authenticated invocation are explicitly deferred to MCP-002.
