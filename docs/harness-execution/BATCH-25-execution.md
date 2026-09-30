# BATCH-25 Execution Record

> Batch: `BATCH-25`
> Task: `TASK-POST-AUDIT-013`
> Start: `2026-08-02 00:00 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- BATCH-24 / TASK-POST-AUDIT-009 is completed with Review verdict `pass`.
- Existing BATCH-14 through BATCH-24 worktree changes are preserved; no reset, checkout, restore, commit, push, deployment, production migration, or external provider probe is permitted.
- This Batch is limited to provider endpoint SSRF/DNS/redirect/egress policy, the authenticated and rate-limited `/models/check` path, unified provider HTTP client construction, focused tests, and this execution record.
- BATCH-26 legacy bypass retirement and real-API Eval hardening remain deferred.

## Baseline

- BATCH-24 baseline: backend `706 passed, 1 skipped, 166 warnings`; Ruff pass; Fast Eval `9/9`; Observability Eval `14/14`; frontend lint `0 errors, 99 warnings`, typecheck pass, Vitest `41/41`, build pass.
- Preflight confirmed the existing BATCH-14 through BATCH-24 dirty worktree was preserved. No commit, push, deployment, or external endpoint probe was performed.

## TDD / implementation

- Red: `uv run --no-cache --directory backend pytest tests/agents/test_provider_endpoint.py tests/acceptance/test_task_post_audit_013_provider_security.py tests/harness/test_model_gateway.py -q --disable-warnings` exited `1` during collection because the new configuration/rate-limit contracts did not yet exist.
- Green focused verification: `22 passed, 22 warnings`; the focused command exited `0`.
- Added an immutable shared provider endpoint policy with canonical host/port/scheme handling, IPv4-mapped IPv6 rejection, DNS multi-answer fail-closed validation, redirect revalidation, and a no-follow HTTP client factory.
- Added cloud startup fail-closed checks requiring DNS resolution and non-empty host/port egress allowlists. Docker Compose declares the public provider host allowlist; local mode retains the explicit localhost development exception.
- Routed primary ModelGateway and `/models/check` provider calls through the shared client policy. `/models/check` now requires `get_current_user`, applies per-user rate limiting, and never returns provider keys, raw exceptions, or endpoint details.
- Added provider-neutral `dns` and `ssrf` safe error categories and bounded user-facing messages. Legacy direct provider paths remain BATCH-26 scope.

## Verification

- `uv run --no-cache --directory backend pytest` exited `0`: `716 passed, 1 skipped, 166 warnings`.
- `uv run --no-cache --directory backend ruff check app tests` exited `0`: all checks passed.
- `uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml` exited `0`: `9/9` passed, `0` failed, `100.0%`.
- `uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml` exited `0`: `14/14` passed, `0` failed, `100.0%`.
- `pnpm.cmd --dir frontend lint` exited `0`: `0 errors, 99 warnings`; `pnpm.cmd --dir frontend typecheck` exited `0`; `pnpm.cmd --dir frontend test` exited `0`: `9 files, 41 tests`; `pnpm.cmd --dir frontend build` exited `0`.
- `git diff --check` exited `0` with existing LF/CRLF working-copy warnings only. No frontend source or dependency changes were introduced.

## Review

- Review verdict: `pass`.
- Review rounds: `1`.
- No blocker, critical, high, or unhandled medium findings. Initial and redirect requests share the same host/port/scheme policy; DNS, metadata, private address, auth, timeout, and rate-limit outcomes are bounded and categorized without raw provider data.

## Handoff

- Batch status: `completed`.
- Changed files: `backend/app/agents/provider_endpoint.py`, `backend/app/api/v1/agent.py`, `backend/app/harness/model_gateway.py`, `backend/app/harness/model_types.py`, `backend/app/harness/decision_parser.py`, `backend/app/core/config.py`, `backend/app/main.py`, `docker-compose.yml`, `backend/tests/agents/test_provider_endpoint.py`, `backend/tests/acceptance/test_task_post_audit_013_provider_security.py`, `backend/tests/harness/test_model_gateway.py`, and this execution record.
- Rollback: revert only the BATCH-25 provider endpoint, provider client, `/models/check`, configuration, and focused test changes after recording a clean validation baseline; preserve BATCH-14 through BATCH-24 changes.
- Next batch: BATCH-26 / TASK-POST-AUDIT-010.
