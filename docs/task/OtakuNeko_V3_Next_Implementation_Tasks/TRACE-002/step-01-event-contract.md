# TRACE-002 Step 01 Event Contract

## Files

- Modify `backend/app/trace/__init__.py`.
- Create `backend/app/trace/redaction.py`.
- Test in `backend/tests/trace/test_event_contract.py`.

## Requirements

Define event types for node start/end, routing decision, capability call,
MCP call, model call, retry, and failure. Events carry correlation_id,
parent_event_id, timestamps, duration, status, and bounded metadata.

The redactor must recursively remove configured secret keys and truncate large
strings and collections. It must run before any TraceStore call.

## Acceptance

- Event ordering and parent relationships serialize deterministically.
- Secret variants such as `api_key`, `authorization`, and `token` are redacted.
- Chain-of-thought fields are rejected rather than persisted.
