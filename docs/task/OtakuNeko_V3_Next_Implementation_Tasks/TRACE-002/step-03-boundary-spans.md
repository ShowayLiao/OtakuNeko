# TRACE-002 Step 03 Capability and MCP Spans

## Files

- Modify `backend/app/capabilities/base.py` or add a wrapper module.
- Modify `backend/app/agents/mcp/adapter.py`.
- Modify `backend/app/mcp_server/__init__.py`.
- Test in `backend/tests/trace/test_boundary_spans.py`.

## Requirements

Record operation name, safe argument shape, result status, duration, retries,
and error category. Keep instrumentation outside business services and avoid
duplicating events when an MCP tool invokes a local capability.

## Acceptance

- One logical call has one parent span and balanced child spans.
- Timeouts and protocol errors are distinguishable.
- Raw review text, memory content, and credentials are absent from traces.
