# MCP-001 Anime MCP Server

## Goal

Establish an Anime-only Model Context Protocol pilot that exposes the existing
AnimeCapability through a stable stdio entry point without widening the
capability security boundary.

## Dependencies

- CAPABILITY-001
- Existing AnimeCapability action descriptors
- CAPABILITY-002 action security metadata for the current fail-closed baseline

## Scope

- Provide an MCP server and stdio entry point for local clients.
- Register only AnimeCapability in the MCP-001 production registry.
- Derive MCP names, descriptions, and input schemas from Anime action
  descriptors.
- Expose the five read-only Anime tools: search, detail, staff, cast, and
  reviews.
- Support the minimum initialize, tools/list, and tools/call pilot flow.
- Preserve capability result contracts when serializing tool results.
- Deny capabilities that require trusted authentication or side-effect policy
  when no trusted MCP invocation context exists.

## Non-Goals

- Exposing schedule, media, recommendation, or every registered capability.
- Accepting user identity or authorization claims from tool arguments.
- Enabling write or delete operations over the anonymous stdio entry point.
- Remote or public MCP hosting.
- Full transport conformance, cancellation, size limits, or authenticated MCP
  sessions; these belong to MCP-002.

## Execution Order

1. Add the MCP server skeleton and Anime-only stdio entry point.
2. Map Anime action descriptors to stable MCP tool definitions.
3. Route tool calls through AnimeCapability and preserve typed failures.
4. Add protocol and capability-boundary tests.

Detailed requirements are split across the step files in this directory.

## Definition of Done

- The MCP-001 entry point registers AnimeCapability and no additional domain.
- tools/list returns exactly the five documented Anime tools with schemas
  derived from action descriptors.
- tools/call routes known tools through AnimeCapability and returns a
  structured capability result.
- Unknown tools and methods fail predictably.
- Protected or side-effecting actions cannot be invoked without trusted MCP
  context and policy support.
- MCP unit tests, MCP lint checks, and the backend regression suite pass.

## Rollback

Disable the MCP stdio entry point and remove its client configuration. The
AnimeCapability and existing in-process tool path remain unchanged because the
pilot is an additive adapter and does not migrate domain ownership.

## Follow-Up

MCP-002 generalizes discovery, introduces authenticated invocation context and
side-effect policy, adds approved schedule and media domains, and hardens the
stdio transport with conformance and subprocess tests.

## Related RFC

RFC-101 Phase 6 and RFC-106 MCP Layer.
