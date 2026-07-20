# MCP-002 Step 01 Capability-Driven Discovery

## Files

- Modify `backend/app/mcp_server/__init__.py`.
- Consume action descriptors from CapabilityRegistry.
- Test in `backend/tests/mcp/test_discovery.py`.

## Requirements

Generate MCP names, descriptions, and input schemas from registered capability
metadata. Validate schemas at server startup and reject duplicate public names.
Only actions explicitly marked MCP-exposed are listed.

## Acceptance

- No domain-specific action list remains in MCPServer.
- Anime tool names and schemas remain compatible.
- Unsupported schemas fail startup with an actionable message.
