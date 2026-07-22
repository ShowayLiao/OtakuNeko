# MCP-002 Step 01 Approved Capability Discovery

## Files

- Modify `backend/app/mcp_server/__init__.py`.
- Consume action descriptors from CapabilityRegistry.
- Test in `backend/tests/mcp/test_discovery.py`.

## Requirements

Build on MCP-001's descriptor-driven Anime mapping by applying an explicit MCP
exposure filter across registered capabilities. Validate public schemas at
server startup and reject duplicate public names. Only actions explicitly
marked MCP-exposed are listed.

## Acceptance

- No domain-specific action list or implicit expose-all policy remains in
  MCPServer.
- Anime tool names and schemas remain compatible.
- Unsupported schemas fail startup with an actionable message.
