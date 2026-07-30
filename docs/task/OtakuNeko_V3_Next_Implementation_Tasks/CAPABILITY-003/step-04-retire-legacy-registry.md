# CAPABILITY-003 Step 04 Retire Legacy Registry

## Files

- Delete `backend/app/agents/registry.py`.
- Remove `ALL_TOOLS` from `backend/app/agents/tools/__init__.py`.
- Remove or narrow the compatibility module
  `backend/app/agents/tools.py`.
- Replace `backend/tests/agents/test_registry.py` with capability/runtime
  adapter coverage.
- Update `backend/tests/agents/mcp/test_integration.py`.
- Extend `backend/tests/architecture/test_dependency_direction.py`.
- Update affected backend documentation.

## Requirements

Delete the legacy registry only after the parity and runtime suites pass.
Individual tool modules may remain as thin compatibility functions only when
an external import still needs them; they must delegate to capability-owned
behavior and must not form another registration list.

Add architecture checks that fail when production code:

- imports `ToolRegistry`;
- defines or imports `ALL_TOOLS`;
- constructs a production `CapabilityRegistry` outside the shared factory,
  except in isolated tests;
- adds a local agent tool with no owning capability action;
- imports domain services directly from the agent or MCP presentation layers.

Update documentation to identify `CapabilityRegistry` as the canonical local
action catalog and the outbound MCP provider as runtime composition, not a
second registry.

## Acceptance

- Repository search finds no production `ToolRegistry` or `ALL_TOOLS`
  references.
- Fresh process startup registers the expected inventory once.
- Architecture tests demonstrate that reintroducing either legacy pattern
  fails.
- Full tests show no chat, MCP, trace, or capability regression.
