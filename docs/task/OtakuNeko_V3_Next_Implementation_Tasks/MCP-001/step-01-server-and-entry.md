# MCP-001 Step 01 Server and Entry Point

## Files

- Create `backend/app/mcp_server/__init__.py`.
- Create `backend/app/mcp_server/entry.py`.

## Requirements

Provide a small JSON-RPC-over-stdio server with an explicit construction path.
The MCP-001 entry point must build an isolated registry containing only
AnimeCapability, then run the server until stdin reaches EOF.

The server must advertise its protocol version and tools capability during
initialization. Protocol frames are written as one JSON object per stdout line;
application diagnostics must not be intentionally written to stdout.

## Acceptance

- The entry point starts without importing the FastAPI application lifecycle.
- Initialization returns server identity, protocol version, and tools support.
- Reaching stdin EOF terminates the server normally.
- Registering future domains requires an explicit MCP entry-point change until
  MCP-002 introduces its approved discovery policy.
