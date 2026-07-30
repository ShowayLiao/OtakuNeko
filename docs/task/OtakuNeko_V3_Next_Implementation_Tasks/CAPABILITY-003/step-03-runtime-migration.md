# CAPABILITY-003 Step 03 Chat Runtime and MCP Composition

## Files

- Modify `backend/app/agents/graph.py`.
- Create or modify a focused outbound-tool provider under
  `backend/app/agents/mcp/`.
- Modify `backend/app/mcp_server/entry.py`.
- Modify `backend/app/mcp_server/__init__.py` only where factory injection
  requires it.
- Update tests under `backend/tests/agents/`, `backend/tests/mcp/`, and
  `backend/tests/trace/`.

## Requirements

Inject `CapabilityRegistry` into `ChatWorkflow` and derive local LangChain
tools through the adapter. Remove `ChatWorkflow`'s direct default construction
of `ToolRegistry` and registration of `ALL_TOOLS`.

Keep outbound MCP discovery as an explicit runtime provider: it may return
adapted remote LangChain tools, but it must not own or duplicate local
capability actions. Compose local and remote tools once per workflow instance,
reject name collisions deterministically, and bind the identical resolved
list to the model and `ToolNode`.

Change MCP server startup to use the shared capability factory while retaining
its independent exposure allowlist and trusted identity/dependency provider.

## Acceptance

- Chat works with local capability tools, no tools, and local plus outbound MCP
  tools.
- Local/remote name collisions fail before model execution.
- Model binding and `ToolNode` receive the same tool instances.
- MCP discovery and exposure remain policy-controlled and do not expose newly
  registered actions by default.
- Streaming event names, tool ids, statuses, duration fields, and trace
  correlation remain backward compatible.
