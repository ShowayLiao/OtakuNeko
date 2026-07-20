# MCP-002 Step 02 Authentication and Side-Effect Policy

## Files

- Create `backend/app/mcp_server/context.py` and `policy.py`.
- Modify MCP dispatch.
- Test in `backend/tests/mcp/test_policy.py`.

## Requirements

Pass authenticated user context separately from tool arguments. Read actions
require ownership scope; write/delete actions require explicit enablement and
idempotency. Never accept user_id from untrusted tool arguments as authority.

## Acceptance

- Anonymous access to protected tools is denied.
- Cross-user arguments cannot widen access.
- Replayed writes do not duplicate effects.
- Denials are traceable without leaking credentials.
