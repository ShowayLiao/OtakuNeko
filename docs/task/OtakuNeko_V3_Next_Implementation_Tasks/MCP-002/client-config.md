# MCP-002 Client Configuration

## Local stdio

Configure the MCP host to launch the server from the backend project. Replace
`<repository>` with the absolute repository path and use forward slashes in
JSON when required by the host.

```json
{
  "mcpServers": {
    "otakuneko": {
      "command": "uv",
      "args": [
        "--directory",
        "<repository>/backend",
        "run",
        "python",
        "-m",
        "app.mcp_server.entry"
      ],
      "env": {
        "DEBUG": "false"
      }
    }
  }
}
```

The server uses stdout exclusively for JSON-RPC frames. Diagnostics go to the
configured application log files and, when debug logging is enabled, stderr.

## Trusted local identity

The stdio process is anonymous by default. To enable approved user-scoped read
tools, the host administrator may bind the process to one local OtakuNeko user:

```json
{
  "env": {
    "DEBUG": "false",
    "OTAKUNEKO_MCP_USER_ID": "42"
  }
}
```

`OTAKUNEKO_MCP_USER_ID` is server-controlled configuration. Tool arguments
cannot authenticate a caller or change this identity. The configured user must
already exist in the selected OtakuNeko database.

Do not place access tokens, passwords, or database credentials in tool
arguments. Use the backend's normal environment configuration for those
secrets.

## Exposure and writes

MCP-002 exposes the five Anime read tools, `schedule_list_schedules`,
`media_library_status`, and `media_list_rss_feeds`. Recommendation actions and
all write/delete actions remain hidden from the production stdio entry point.

The internal dispatcher additionally requires trusted authentication, explicit
side-effect approval, and an idempotency key before an approved write can run.
Enabling production writes requires a separate exposure review and host consent
flow; adding a tool name to client arguments cannot enable them. Its bounded,
24-hour in-memory replay cache protects only the lifetime of one server process.
Production write exposure therefore also requires durable, database-backed
idempotency across restarts and multiple server processes.

## Verification

From `backend`:

```bash
uv run pytest tests/mcp/test_stdio_e2e.py -q
```
