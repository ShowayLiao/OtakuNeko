---
name: frontend-qa
description: Use when auditing, testing, fixing, or reviewing OtakuNeko frontend user flows, especially Agent chat, SSE, session state, responsive layout, or browser regressions.
---

# OtakuNeko frontend QA

Use repository-root paths below. Read root and path-specific AGENTS instructions first; this skill does not authorize production actions, commits, pushes, or changes to external task managers.

## Establish evidence before editing

1. Run `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git worktree list`. Attribute existing edits; preserve parallel work. Ask about unknown changes before implementation. Do not invent a Harness Batch for this workflow.
2. Read actual `frontend/package.json`, test/Next configs, routes, components, stores, API client and backend response schemas. For Harness-related work read the three architecture/review references required by AGENTS.
3. Discover available browser tools. Use **agent-browser MCP**, falling back to an isolated named agent-browser CLI session. Do not substitute Playwright MCP. Playwright **Test** is the regression runner. Prefer existing Chromium; use `E2E_CHROMIUM_EXECUTABLE_PATH` for an explicitly located local executable if the download is unavailable. Report the actual version and local/CI difference.
4. Establish unit/browser baseline. Run the app, inspect snapshot, perform interactions, capture screenshots, read Console/errors and Network. CLI commands include `agent-browser --session <unique-name> open <url>`, `snapshot -i`, `console`, `errors`, `network requests`, `set viewport <w> <h>`, `screenshot <absolute-path>`. Quote `@refs` in PowerShell. Never treat test listing or HTTP 200 as browser acceptance.

## Inventory and acceptance

Maintain `docs/frontend-qa/feature-inventory.md`, `acceptance-matrix.md`, `audit-report.md`. Give each feature a stable ID, source symbol/path, user path, expected vs observed behavior, implementation evidence, severity, and test evidence. Separate reproducible defects, existing limits, and product decisions. Do not infer live run recovery from a unit test with a pre-seeded run ID. Anonymous sessions are intentionally temporary.

For each fix batch state allowed files, acceptance criteria and rollback. Follow:

`discover -> inventory -> acceptance -> browser reproduction -> failing regression -> minimal fix -> regression -> independent Review -> browser recheck -> report`

Run one fix batch at a time. Use settled, disjoint work orders when delegating. The coordinator owns protocol/security/concurrency choices and final acceptance.

## Test execution

From repository root:

```powershell
pnpm --dir frontend test:e2e
uv sync --directory backend --locked --dev
pnpm --dir frontend test:e2e:smoke
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
```

Install frontend dependencies with pnpm **10.15.1**; `pnpm --dir frontend exec playwright install chromium` installs the locked Playwright browser. CI installs Chromium system dependencies too. Core Mock tests do not require backend dependencies. Smoke config creates its own backend and frontend; ports **3100/8100** must be free. Do not stop unrelated services to free a port.

`frontend/e2e/fixtures.ts` supplies synthetic API routes and a controllable real HTTP SSE response. Match `backend/app/api/v1/agent.py` and `frontend/src/lib/fetcher.ts`: event names, sequence/cursor, durable markers, tool invocation IDs, terminal status, replay JSON. Assert intermediate state before releasing the next SSE phase. A buffered `route.fulfill` verifies framing/final state, not incremental delivery. Assert no duplicate chat POST during replay and no success after failure/cancel/timeout. Unexpected API routes and page exceptions fail tests.

Cover Empty/Loading/Success/Error, tool details, cancellation/recovery, sessions, refresh, keyboard/duplicate-send paths and affected layout. Desktop **1440x900**, tablet **768x1024**, mobile **390x844** require real rendered checks. Wait for library CSS to apply before measuring controls; verify Send and Stop bottom bounds after toolbar wrapping, and reserve composer space so messages cannot be obscured. For hydration/layout changes inspect a production build too using an explicitly started local QA server and E2E_EXTERNAL_SERVER=1. Check clickability/containment as well as screenshots; `toBeVisible` alone does not prove an offscreen control is reachable.

Smoke runs `frontend/e2e/start-backend.mjs`: real FastAPI, temporary SQLite/checkpoint files, fresh JWT, no inherited provider credentials/.env, qB and scheduler disabled. Use new synthetic accounts/data. Never point smoke at a production/existing personal backend. Current smoke proves auth/HTTP/history integration, not real LLM reasoning or tool execution.

## Review and evidence

After relevant lint/typecheck/unit/build/E2E checks, ask an independent reviewer with fresh context to inspect the **complete task diff and untracked files**, excluding explicitly attributed parallel edits. Review state races, React lifecycle, SSE/API compatibility, authorization boundaries, accessibility, visual regressions and false-positive tests. Reviewer does not edit. Remediate findings, rerun affected checks and re-review; stop after three unsuccessful review rounds as AGENTS requires. If independent review cannot run, state that limitation and provide `/review` scope; self-check is not independent Review.

Re-execute affected user paths using agent-browser after Review. Inspect final screenshots, Console and Network. Persist evidence under ignored `.runtime/frontend-qa` only; use synthetic data for Playwright traces because traces retain bodies/DOM and credentials. Never capture real keys, tokens or personal histories. CI evidence expires after seven days. Diagnostics omit request bodies/headers and query strings; network failure logs alone are not an assertion.

Report exact commands, exit codes, counts/warnings and skipped checks/reasons. Missing exit code means UNKNOWN. Distinguish **已通过浏览器验证 / 仅通过 Mock 测试 / 未验证 / 已知失败**; add separate unit and real backend smoke results. Mock browser success proves frontend consumption of fixture data, not actual Agent business capability. Keep remaining limitations explicit and link artifacts. Do not claim CI passed from inspecting YAML. Do not commit or publish without authorization.
