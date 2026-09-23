# Review Remediation Implementation Plan

> **For the implementing agent:** Execute this plan in the current `feature-harness` checkout. Preserve all existing user changes and stage files explicitly.

**Goal:** Correctly distinguish expired user authentication from missing provider configuration, reject invalid collection subject types at the HTTP boundary, verify the complete Harness change set, and commit it.

**Architecture:** Reuse the backend's existing `WWW-Authenticate: Bearer` signal to classify chat authentication failures without changing provider-configuration semantics. Bind the dashboard query directly to the existing `SubjectType` enum so FastAPI rejects values outside `1, 2, 3, 4, 6` before the service runs.

**Tech stack:** TypeScript/Vitest, FastAPI/Pydantic/Pytest, Git.

---

### Task 1: Distinguish chat authentication failures

**Files:**
- Modify: `frontend/src/lib/fetcher.test.ts`
- Modify: `frontend/src/lib/fetcher.ts`
- Modify: `frontend/src/app/api/v1/chat/route.test.ts`
- Modify: `frontend/src/app/api/v1/chat/route.ts`

- [x] Add a Vitest case where `/chat` returns `401` with `WWW-Authenticate: Bearer`; assert `authentication_error` and removal of the stored user token.
- [x] Run the focused test directly with the repository's Vitest binary and confirm the new assertion fails for the current implementation (`1 failed, 31 passed`).
- [x] Update chat error classification to treat a Bearer challenge as user-authentication failure while preserving a headerless `Missing API Key` response as `configuration_error`.
- [x] Add a proxy regression test, confirm that the frontend route dropped the upstream `WWW-Authenticate` header, then forward the challenge so the browser can perform the classification on the real request path.
- [x] Rerun the focused proxy and fetcher tests and confirm they pass (`34 passed`).

### Task 2: Reject invalid collection subject types

**Files:**
- Modify: `backend/tests/api/test_dashboard_statistics.py`
- Modify: `backend/app/api/v1/dashboard.py`

- [x] Add an HTTP-level test that requests `subject_type=5` and expects `422` without invoking the statistics service.
- [x] Run the focused pytest case and confirm it fails against the current `ge=1` query constraint (`200` instead of `422`).
- [x] Type the query parameter as `SubjectType` with `SubjectType.ANIME` as the default and pass its integer value to the service.
- [x] Rerun the focused backend test and confirm it passes (`2 passed`).

### Task 3: Verify, review, and commit

**Files:**
- Review every staged, unstaged, and untracked file in the current task scope.

- [x] Run the backend tests. Result: `745 passed, 1 skipped, 242 warnings` from the final full run. An earlier attempt saw a transient Bangumi timeout; rerunning the complete suite succeeded.
- [x] Run `uv run --directory backend ruff check app tests` (`All checks passed!`).
- [x] Run the frontend lint, typecheck, test, and build scripts through their repository-local binaries because the `pnpm` wrapper hung in this environment. Result: lint `0 errors, 94 warnings`; typecheck passed; `96 passed`; production build passed.
- [x] Run `git diff --check`, `git diff --cached --check`, inspect full diffs, and request an independent read-only code review. Final verdict: `pass`; no Blocker/Critical/High/Medium findings. Removed the duplicate `.runtime/` ignore entry noted as Low.
- [x] With the review verdict passing and no unresolved Medium-or-higher findings, explicitly stage all task files and create the authorized local commit without bypassing hooks.

### Review remediation notes

- The first independent review found that the new streaming path did not request provider usage metadata. A regression assertion failed with `KeyError: stream_options`; the adapter now defaults to `stream_options={"include_usage": True}` while preserving an explicit caller override, and the focused test passes.
- The first independent review also found that the README implied remote MCP/Workflow were already main-chat Dispatcher targets. The architecture diagram and comparison table now state the current separate MCP Exposure Map/Policy boundary and the unconnected status of remote MCP/Workflow.
