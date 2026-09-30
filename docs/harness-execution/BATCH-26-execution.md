# BATCH-26 Execution Record

> Batch: `BATCH-26`
> Task: `TASK-POST-AUDIT-010`
> Start: `2026-08-02 00:20 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- BATCH-25 / TASK-POST-AUDIT-013 is completed with Review verdict `pass`.
- Existing BATCH-14 through BATCH-25 worktree changes are preserved; no reset, checkout, restore, commit, push, deployment, production migration, or real external provider probe is permitted.
- This Batch is limited to legacy-entry inventory and fail-closed retirement, default Runtime-owned cutover, primary API fake-provider Acceptance/Eval, and final hardening.
- No target-architecture document will be changed to claim implementation until this Batch has a passing Review and real verification.

## Baseline

- BATCH-25 baseline: backend `716 passed, 1 skipped, 166 warnings`; Ruff pass; Fast Eval `9/9`; Observability Eval `14/14`; frontend lint `0 errors, 99 warnings`, typecheck pass, Vitest `41/41`, build pass.
- Current source fact before implementation: `_primary_decision_loop_enabled()` defaulted to `False`; `/chat` created `ChatWorkflow` and selected `runtime.stream()` when the flag was absent. The primary `stream_decision()` path and canonical persistence existed but were not the default route.
- Current source fact before implementation: `ChatWorkflow` owned a compatibility LangGraph loop and proposal-only ToolNode wrappers; the default-cutover test had to prove the primary API did not instantiate that graph.

## TDD / implementation

- Red: the new default-cutover and specialist-boundary collection exited `1` with `5 failed`: the default was still false, `/chat` still constructed `ChatWorkflow`, and enabled specialist routing still called `agent.execute()` directly.
- Green focused verification: API cutover, primary resume fail-closed, approval, unknown-outcome, and prompt-injection coverage `10 passed`; MCP/scheduler entrypoint and existing MCP policy/protocol regression collection `48 passed`; Ruff passed.
- Final remediation red/green: the approval scenario first exposed that `approval_required` was metadata-only in `PolicyEngine`; after enforcing the trusted approval check, the focused API/policy collection passed `30/30`.
- Changed the primary `/chat` path to default to `AgentRuntime.stream_decision()` and to avoid constructing or compiling `ChatWorkflow`, `LangGraphAdapter`, or the compatibility specialist router. The explicit `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=false` value remains the rollback to the verified compatibility adapter. The default `/chat/resume` Workflow entrypoint now fails closed with a clear 409 until a Runtime-owned approval-resume contract exists.
- Routed MCP execution through a per-call `Dispatcher` with trusted `ExecutionContext`, policy/approval/idempotency, dependency injection, normalized model projection, and the existing v1 `data` envelope. Outer asyncio cancellation is preserved by the Dispatcher.
- Enforced `ActionDescriptor.approval_required` in `PolicyEngine`; missing or mismatched trusted approval now fails closed before capability execution.
- Removed the scheduler `_SpecialistAdapter` direct execution path and made un-migrated specialist routing fail closed with a Dispatcher-required error. Updated the router contract and acceptance tests to prove discovery does not imply execution.
- Added main API fake-provider Eval coverage for ordinary response, read-only tool invocation, denied protected capability, provider failure, tool timeout, and cancellation-before-model. Legacy API tests now set the explicit rollback flag when they intentionally exercise `ChatWorkflow` compatibility behavior.

## Verification

- `$env:DEBUG='false'; uv --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' run pytest` exited `0`: `728 passed, 1 skipped, 165 warnings` (729 collected).
- `uv --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' run ruff check app tests` exited `0`: all checks passed.
- Focused primary API fake-provider Eval exited `0`: `7 passed, 21 warnings`; entrypoint/MCP focused collection exited `0`: `48 passed, 19 warnings`.
- `uv --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' run python -m app.evaluation.runner --config evals/config/fast.yaml` exited `0`: `9/9` passed, `0` failed, `100.0%`.
- `uv --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' run python -m app.evaluation.runner --config evals/config/observability.yaml` exited `0`: `14/14` passed, `0` failed, `100.0%`.
- `pnpm.cmd --dir frontend lint` exited `0`: `0 errors, 99 warnings`; `pnpm.cmd --dir frontend typecheck` exited `0`; `pnpm.cmd --dir frontend test` exited `0`: `9 files, 41 tests`; `pnpm.cmd --dir frontend build` exited `0`.
- `git diff --check` exited `0`; only existing LF/CRLF working-copy warnings were reported.

## Review

- Review verdict: `pass`.
- Review rounds: `2` (initial implementation review plus final fail-closed approval/resume remediation review).
- No blocker, critical, high, or unhandled medium findings. The default path is Runtime-owned and canonical SSE is a projection of Runtime events; the compatibility graph is only reachable through the explicit rollback flag and its tool wrappers remain proposal-only.

## Handoff

- Batch status: `completed`.
- Changed files: `backend/app/api/v1/agent.py`, `backend/app/agents/router.py`, `backend/app/harness/dispatcher.py`, `backend/app/harness/policy.py`, `backend/app/harness/routing_adapter.py`, `backend/app/harness/scheduler/execution.py`, `backend/app/mcp_server/__init__.py`, `backend/tests/acceptance/test_task_post_audit_010_api_cutover.py`, `backend/tests/acceptance/test_task_post_audit_010_entrypoints.py`, `backend/tests/acceptance/test_restart_recovery.py`, `backend/tests/agents/test_multi_agent_integration.py`, `backend/tests/harness/test_api_regression.py`, `backend/tests/mcp/test_stdio_e2e.py`, `backend/tests/memory/test_api.py`, and this execution record.
- Deferred findings: the LangGraph/RecommendationAgent compatibility implementation remains available for explicit rollback and isolated unit coverage; un-migrated specialist and scheduler production entrypoints are intentionally unavailable and fail closed until a Dispatcher-backed subagent contract is implemented. SQLite remains the declared single-worker adapter; no multi-worker deployment claim is made.
- Rollback: set `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=false` only after recording a clean baseline; this returns to the verified compatibility adapter whose proposal-only tools still call the Dispatcher, and must not disable redaction, policy, approval, timeout, cancellation, idempotency, audit, or canonical persistence.
- Next batch: none; after Review, perform final handoff and goal completion.
