# TRACE-002 Step 02 Runtime and Agent Instrumentation

## Files

- Modify `backend/app/harness/runtime.py`.
- Modify `backend/app/agents/langgraph_adapter.py`.
- Modify `backend/app/agents/graph.py` only at stable node boundaries.
- Test in `backend/tests/trace/test_agent_instrumentation.py`.

## Requirements

Use an injected trace recorder or context object; do not import API globals into
harness or agent modules. Emit balanced start/end events even on exceptions and
generator cancellation. Preserve the original exception and stream chunks.

## Acceptance

- Successful, failed, and cancelled streams produce consistent terminal state.
- Node names and routing outcomes are observable without storing private prompts.
- Runtime behavior is unchanged when tracing is disabled.
