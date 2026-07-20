# MCP-002 Step 03 Domains and Transport Hardening

## Files

- Modify `backend/app/mcp_server/entry.py`.
- Register approved schedule and media capabilities.
- Harden stdio request handling.
- Test in `backend/tests/mcp/test_stdio_e2e.py`.

## Requirements

Support initialization, notifications, list, call, malformed JSON, unknown
method, cancellation, and clean EOF. Protocol output must be isolated from
application logs. Limit request and response sizes.

## Acceptance

- A real subprocess client completes initialize/list/call/shutdown.
- Malformed input does not terminate the server.
- Logs never corrupt stdout protocol frames.
