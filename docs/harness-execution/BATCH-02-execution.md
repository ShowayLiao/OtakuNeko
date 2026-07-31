# BATCH-02 Execution Record

> Batch: `BATCH-02`
> Task: `TASK-HARNESS-002`
> Start: `2026-07-31 23:16:15 +08:00`
> Branch: `feature-harness`
> Start commit: `9ffa22ebdf7a0a2948370aa04fe3a5ca448b67fe`
> Record status: `ready_for_commit`

## 1. Preflight

### Workspace and prerequisites

- `git status --short`: clean before implementation.
- `git branch --show-current`: `feature-harness`.
- `git rev-parse HEAD`: `9ffa22ebdf7a0a2948370aa04fe3a5ca448b67fe`.
- Normal checkout; no linked worktree; no nested `AGENTS.md`.
- Previous Batch: BATCH-01 completed; implementation commit `57da25a`, handoff record commit `9ffa22e`.
- BATCH-02 is the only eligible next Batch after BATCH-01 in `docs/harness-tasks/INDEX.md`.
- Allowed changes: `backend/app/harness/contracts.py`, `task.py`, `state.py`, `result.py`, `backend/app/agents/langgraph_adapter.py`, and the listed harness/adapter tests; the required execution record is also maintained.
- Forbidden changes: `backend/app/api/v1/agent.py` SSE structure, `backend/app/agents/graph.py` node/model/ToolNode behavior, database migrations, frontend, all Tool registration/domain services, raw reasoning/CoT in contracts.

### Authority and source facts checked

- `AGENTS.md`
- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/00-executive-summary.md` through `11-task-backlog.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-02/TASK-HARNESS-002.md`
- `docs/code-review.md`
- `docs/harness-execution/README.md` and `TEMPLATE.md`
- Actual source: `AgentTask`, `AgentState`, `AgentResult`, `LangGraphAdapter`, and Graph chunk vocabulary.

### Baseline

| Command | Exit | Result | Notes |
|---|---:|---|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_chat_schema.py -q` | 0 | 44 passed | 22 existing Pydantic/pytest-cache warnings |
| `uv run --no-cache --directory backend ruff check app/harness/task.py app/harness/state.py app/harness/result.py app/agents/langgraph_adapter.py tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_chat_schema.py` | 0 | passed | All checks passed |

## 2. Source facts and implementation

### Source facts

| Symbol | Current fact | Handling |
|---|---|---|
| `AgentTask` / `AgentState` | Existing task/state models have no versioned Run/Invocation/Event contract. | Preserve them and add a wrapper contract layer. |
| `AgentResult.from_raw` | Accepts legacy dict/non-dict values and already excludes `content` from `prompt_payload`. | Add explicit `InvocationResult` conversion and hide raw exceptions. |
| `LangGraphAdapter` | Existing `stream` and `execute` forward/collect raw chunks and trace them; Graph owns the chunk vocabulary. | Add pure conversion functions only; leave old chunk and Graph behavior unchanged. |

### TDD evidence

- Tests were added before production implementation.
- The red run failed at collection because `contracts.py` and the adapter functions did not exist; no tests were weakened or bypassed.

### Changes

- Added versioned Pydantic v2 contracts: `RunRequest`, `ExecutionContext`, `AgentDecision`, `InvocationRequest`, `InvocationResult`, `RunEvent`, `RunResult`, and the ten required error codes.
- Added factory defaults for mutable dictionaries/lists, JSON serialization, identity-field validation, and trusted `ExecutionContext.principal_id`.
- Added explicit `AgentResult.from_invocation_result` conversion and safe handling of raw exceptions; legacy raw dict compatibility remains.
- Added pure `adapt_langgraph_event` / `adapt_langgraph_events` functions that preserve stable sequence and invocation IDs while omitting raw tool output and error detail.
- Did not modify `AgentTask`, `AgentState`, Graph nodes, API SSE, database, frontend, dependencies, or Tool registration.

## 3. Verification

| Command | Exit | Result | Known warnings/notes |
|---|---:|---|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_chat_schema.py -q` | 0 | 52 passed | 22 existing Pydantic/pytest-cache warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 519 passed | 110 existing warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | passed | All checks passed |
| `$env:DEBUG='false'; uv run --no-cache --directory backend python -c "from app.main import app; ..."` | 0 | backend app import smoke passed | No external service started |

No real provider, external network, production deployment, or API SSE flow was changed or invoked; task scope forbids those side effects and forbids the API/Graph files.

## 4. Review

Review follows `docs/code-review.md`: the complete tracked diff, all three untracked files, scope, trailing-whitespace/secret scans, forbidden-path check, and verification output were inspected. Review did not modify code.

```yaml
review_result:
  batch: BATCH-02
  verdict: pass
  summary: "完整 diff、契约字段、adapter 脱敏、兼容边界和允许范围复核通过；无 blocker、critical、high 或 medium finding。"
  findings: []
  reviewed_commands:
    - "git status --short"
    - "git diff --check"
    - "git diff --stat"
    - "git diff"
    - "uv run --no-cache --directory backend pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_chat_schema.py -q"
    - "uv run --no-cache --directory backend pytest -q"
    - "uv run --no-cache --directory backend ruff check app tests"
    - "uv run --no-cache --directory backend python -c \"from app.main import app; ...\""
  reviewed_files:
    - "backend/app/harness/contracts.py"
    - "backend/app/harness/result.py"
    - "backend/app/agents/langgraph_adapter.py"
    - "backend/tests/harness/test_contracts.py"
    - "backend/tests/harness/test_result_contract.py"
    - "backend/tests/agents/test_langgraph_adapter.py"
    - "docs/harness-execution/BATCH-02-execution.md"
  deferred_findings:
    - "Contracts are not yet the sole Runtime coordinator; actual integration remains deferred to BATCH-05."
```

## 5. Handoff

```yaml
batch_result:
  batch: BATCH-02
  status: ready_for_commit
  commit: null
  tasks_completed:
    - TASK-HARNESS-002
  tests:
    passed:
      - "specified regression: 52"
      - "backend full pytest: 519"
      - "backend ruff"
      - "backend app import smoke"
    failed: []
    skipped:
      - "real provider/API SSE flow: forbidden or unchanged by task scope"
  review:
    verdict: pass
    rounds: 0
    deferred_findings:
      - "Runtime/Registry integration deferred to later dependent Batches."
  changed_files:
    - backend/app/harness/contracts.py
    - backend/app/harness/result.py
    - backend/app/agents/langgraph_adapter.py
    - backend/tests/harness/test_contracts.py
    - backend/tests/harness/test_result_contract.py
    - backend/tests/agents/test_langgraph_adapter.py
    - docs/harness-execution/BATCH-02-execution.md
  unresolved_risks:
    - "This Batch defines and adapts contracts but does not change the current LangGraph loop owner."
  next_batch: BATCH-03
```
