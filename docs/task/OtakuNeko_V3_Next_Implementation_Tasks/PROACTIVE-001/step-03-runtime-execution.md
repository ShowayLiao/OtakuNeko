# PROACTIVE-001 Step 03 Runtime Execution and Policy

## Files

- Create a scheduled-task adapter to AgentTask.
- Modify `backend/app/harness/runtime.py` only through stable extension points.
- Create `backend/app/harness/policy.py` if not already present.
- Test in `backend/tests/proactive/test_execution.py`.

## Requirements

Execute through AgentRuntime and AgentRouter with per-task timeout, model/call
budget, capability allowlist, and idempotency context. External writes require
pre-approved policy. Retry only categorized transient failures with backoff.

## Acceptance

- Success, permanent failure, transient retry, timeout, and cancellation have
  deterministic final states.
- Side effects are not repeated across retries.
- Run traces link task id, run id, user id, and scheduled slot.
