# CAPABILITY-003 Canonical Capability Registry

## Goal

Make `CapabilityRegistry` the single source of truth for local agent actions
and retire the parallel `ToolRegistry`/`ALL_TOOLS` catalog without changing
public tool names, schemas, tracing, or MCP behavior.

## Dependencies

- CAPABILITY-002
- MCP-002
- TRACE-002

## Scope

- Action lookup and duplicate guarantees in `CapabilityRegistry`.
- A LangChain adapter derived from capability action descriptors.
- One shared capability-registry factory for chat and MCP entry points.
- Explicit composition of capability-derived local tools and outbound MCP
  tools without creating a second local action registry.
- Migration of `ChatWorkflow` away from `ToolRegistry` and `ALL_TOOLS`.
- Removal of obsolete exports, tests, and compatibility paths after parity is
  proven.

## Non-Goals

- Moving reasoning, routing, prompts, or agent selection into capabilities.
- Exposing every capability action over MCP.
- Renaming public tools merely to match internal capability method names.
- Combining outbound MCP connection lifecycle with the capability catalog.
- Removing compatibility before schema and behavior parity tests pass.

## Execution Order

1. Freeze the old-tool to capability-action parity contract.
2. Add capability lookup, LangChain adaptation, and a shared registry factory.
3. Migrate chat runtime and external MCP tool composition.
4. Remove the legacy registry/catalog and enforce architecture guardrails.

## Definition of Done

- Chat and MCP construct local actions from the same capability registry
  factory.
- Every retained chat tool has one owning capability action and preserves its
  public name, description, input schema, result semantics, and trace span.
- No production module imports `app.agents.registry.ToolRegistry` or
  `ALL_TOOLS`.
- Duplicate capability and action names still fail at startup.
- Outbound MCP tools remain discoverable without becoming a second catalog of
  local domain actions.
- Agent, capability, MCP, trace, and architecture tests pass.

## Rollback

Keep the old registry behind a short-lived compatibility factory until parity
tests pass. If runtime regressions appear, restore the compatibility factory
without reverting capability implementations or MCP exposure policy. Delete
the old modules only in the final guarded step.

## Related Tasks

CAPABILITY-001, CAPABILITY-002, MCP-001, MCP-002, TRACE-002.
