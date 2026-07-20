# MCP-002 Capability Discovery and Additional MCP Domains

## Goal

Generalize the Anime MCP pilot so MCP tools are derived from capability action
metadata and expose approved schedule and media operations safely.

## Dependencies

- MCP-001
- CAPABILITY-002
- TRACE-002

## Scope

- Replace hard-coded Anime action lists with registry discovery.
- Expose selected ScheduleCapability and MediaCapability actions.
- Add authentication context and side-effect policy.
- Harden stdio protocol behavior and document client configuration.
- Add protocol conformance and end-to-end tests.

## Non-Goals

- Exposing every internal capability.
- Remote public MCP hosting without a separate threat model.
- Bypassing REST authorization or domain ownership rules.

## Execution Order

1. Generate tool schemas from action descriptors.
2. Add authenticated invocation context and policy.
3. Map schedule and media actions.
4. Harden transport lifecycle and errors.
5. Add conformance, security, and client integration tests.

## Definition of Done

- Adding a registered action requires no MCPServer hard-coded action edit.
- Side-effecting calls require authorization and explicit policy approval.
- Protocol errors follow JSON-RPC/MCP semantics.
- Existing Anime MCP clients remain compatible.

## Rollback

Stop exposing newly registered schedule and media actions and restore the
MCP-001 Anime-only registry and transport path; leave capability metadata
changes inactive until compatibility tests pass.

## Related RFC

RFC-101 Phase 6 and RFC-106 MCP Layer.
