# Agent evaluations

Run the deterministic PR gate from `backend/`:

```bash
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
```

The command executes fixtures through `AgentRuntime`, requires no network or
secrets, writes a machine-readable report under `.runtime/evaluation/`, and
returns non-zero when a configured threshold or baseline regresses.

Run the Runtime entrypoint gate from `backend/` with:

```bash
uv run python -m app.evaluation.runner --config evals/config/entrypoint.yaml
```

This offline target feeds structured decisions from a deterministic model
double into the shared Runtime factory. It dispatches one synthetic read-only
capability, stores runs and traces in a fresh in-memory SQLite database per
case, and checks the persisted trace and terminal run result before returning
evaluation metrics. It does not use `DATABASE_URL`, provider credentials, or
network access.

The entrypoint model double
(`app.evaluation.scripted_llm.ScriptedLLM`) is observation-aware: after N
invoke fixture events, the next model call must see exactly N untrusted
capability feedback messages, and the model-safe context must carry the same
run/trace identity. An invoke event, or a following `tool_call_end`, may set
`output` to the expected normalized capability data; the following step then
checks it against `safe_output`. Feedback must carry the Runtime envelope
(`safe_output` and `provenance`); a user message that only copies the marker is
rejected. Missing, malformed, or tampered feedback fails the case with
`ScriptedObservationError` instead of replaying the script by index. Fixtures
without `output` remain valid.

HTTP debugging uses the same primary execution composition: submit a chat to
`POST /api/v1/chat`, take its `run_id` from SSE, then query
`GET /api/v1/runs/{run_id}`, `GET /api/v1/runs/{run_id}/events`, and
`GET /api/v1/trace/{run_id}` with the same authenticated owner. Trace queries
do not execute the model or tools. Trace is a safe diagnostic projection;
Run/Event persistence remains authoritative. A terminal checkpoint recovery
can rebuild the projection from confirmed events. SQLite recovery retains
the existing single-worker restriction.

The network-backed production evaluation target also uses the shared
composition and a separate in-memory database per case. Its fixture user does
not select a user or business data from the application's configured database;
side effects are disabled. The original fast/observability targets remain
fixture-normalization regressions and do not replace this entrypoint gate.

`full.yaml` explicitly loads the production `ProductionRuntimeTarget` and an
OpenAI-compatible Judge through configured factories. It requires provider
credentials, runs sequentially within the configured concurrency ceiling, and
enforces both a per-call cost reservation and a total Judge budget. Provider
responses and credentials are never copied into reports.

Published datasets, baselines, and threshold configuration are append-only.
Create a new version instead of overwriting an approved version.

## Deterministic case and scoring contract

`evals/datasets/v1-l5-contract.jsonl` adds an optional, versioned
`deterministic` block to an `EvalCase`. It is scored by
`app.evaluation.scoring.score_deterministic`, a pure function of the case spec
and the normalized Runtime result:

| Dimension | Observable |
| --- | --- |
| `termination` | terminal status, optional `error_code` / `termination_reason` |
| `required_tools` / `forbidden_tools` | invoked capability names |
| `arguments` | required/forbidden argument **key names**; values are never read |
| `evidence` | required/forbidden evidence markers |
| `recovery` | whether the Runtime recovered |
| `steps` | `model_decision` count within explicit min/max |
| `tool_errors` | failure count, allowed and required error codes |

`task_success` is the rollup of those dimensions. `answer_quality` is a
separate `AnswerQualitySpec`: only a Judge scores it, and its outcome never
changes `DeterministicScore`. `required` only controls whether an unavailable
Judge fails the case; an available score below `min_score` always fails. Cases
without a `deterministic` block keep the pre-existing metric behavior and are
not scored.

Run the contract gate through the same Runtime entrypoint used by HTTP chat:

```bash
uv run python -m app.evaluation.runner --config evals/config/l5-contract.yaml
```

Each `CaseResult` carries `deterministic` (per-dimension pass/detail and
`task_success`); execution exceptions still produce a failed deterministic
score so the failed dimensions remain visible in the report.

## Versioned L5 scenario dataset

`evals/datasets/v1-l5-scenarios.jsonl` is the versioned behavior dataset. It
contains four fixed synthetic questions with unique fixture users (920–923),
isolated in-memory SQL per case, and deterministic expectations:

| Case | Behavior |
| --- | --- |
| `l5-scenario-single-step` | one model decision, no tools |
| `l5-scenario-multi-step` | two read invocations, then respond |
| `l5-scenario-error-recovery` | one `read_failure`, read retry, completed |
| `l5-scenario-write-approval` | approval pause, one approved write, respond |

Write cases declare `approvals: [{"action": "write"}]`. The trusted principal is
always the isolated fixture user; approval IDs come from the Runtime pause event,
never from model arguments. Approval cases use a discarded per-case SQLite
checkpoint so the paused Run can resume. A completed Run with observed tool
failures is recorded as recovered; cases that allow error codes are not treated
as hard execution failures. Run the dataset through the same Runtime entrypoint:

```bash
uv run python -m app.evaluation.runner --config evals/config/l5-scenarios.yaml
```

## L5 PR benchmark gate

The PR gate runs both L5 configurations through the real Runtime entrypoint,
enforces their thresholds, and compares per-case outcomes with the committed
baseline:

```bash
uv run python -m app.evaluation.l5_gate \
  --report .runtime/evaluation/l5-gate.json \
  --diff .runtime/evaluation/l5-gate-diff.json
```

The gate exits non-zero on a failed case, a threshold failure, or baseline
drift (regression, added case without baseline, or a baseline case missing from
the report). `l5-gate.json` records each case with `case_id`, `run_id`,
`trace_id`, terminal/route facts and failed dimension details, so a failure is
localized without reading raw provider payloads. `l5-gate-diff.json` is the
machine-readable baseline diff. CI job `l5-pr-benchmark-gate` runs it offline
and uploads the JUnit file and both reports; `repository-quality` depends on it.

## Per-case transcripts

Configs with `transcript_dir` (the L5 configs use
`.runtime/evaluation/transcripts`) write one redacted JSON artifact per case
under `transcript_dir/<config-name>/<case-id>.json`. The artifact is written on
both success and failure and contains:

- the fixed synthetic input messages and memory fixtures;
- Decisions (argument **keys** only) and Invocations with their observations;
- normalized Result, ordered stream events, persisted Run events, Trace
  projection, terminal state and a safe error category;
- `case_id`, `run_id` and `trace_id` at the top level for correlation.

Secret keys and chain-of-thought fields are removed, strings/collections are
bounded, raw argument values and provider payloads are never exported, and the
Trace projection uses the stricter trace redaction policy. The CI
`l5-pr-benchmark-gate` job uploads `backend/.runtime/evaluation/transcripts/`
even when the gate fails.

## Offline loop certification

Run the seven synthetic loop scenarios through the same `build_runtime` factory
used by HTTP chat:

```bash
uv run python -m app.evaluation.loop_gate --output .runtime/agent-gate
```

The catalog covers multi-step observation-derived calls, corrected read failures,
policy refusal, approval pause/resume, cancellation before and during execution,
and an unknown write outcome replayed with the same idempotency key. Registry,
Context, Dispatcher, SQL Run/Event/Invocation stores and SQL Trace are real;
only the model and domain capability are synthetic. Databases are isolated and
discarded. Outbound sockets/DNS are blocked; ASGI requires no socket. Windows
asyncio's private stdlib `socketpair` remains available as local process IPC.

Shared primary composition enables trusted `RecoveryPolicy(read_only_errors=True)`.
Only explicitly classified `read_failure`, `transient`, and `rate_limited` failed
reads become observations. Permission failures, unknown outcomes, timeouts,
internal errors and output-contract errors remain terminal. Unchanged failed
actions are blocked before another execution; changed arguments may proceed
within the existing Run budgets. Failure counters are checkpointed as argument
hashes. `RecoveryPolicy(read_only_errors=False)` restores terminal read failures.
Low-level `AgentRuntime` callers retain the legacy opt-in when no policy is supplied.

Artifacts under `.runtime/agent-gate/` include the machine-readable aggregate
report and `cases/<case-id>.replay.json`. Bundles contain only synthetic fixture
messages, observed Decisions, capability arguments/results, ordered persisted
events, Trace and terminal facts. They do not enable production raw Prompt or
provider-payload logging. Available evidence is exported even on case failure.
`read_replay` validates event order and terminal consistency without executing
models or capabilities. To rerun one known synthetic case in a fresh database:

```bash
uv run python -m app.evaluation.loop_gate --replay .runtime/agent-gate/cases/multi_step.replay.json --output .runtime/agent-gate-rerun
```

Replay input is restricted to the fixed synthetic catalog; it cannot select
arbitrary imports, network endpoints or production capabilities. Generated IDs
and timing may differ between runs. Failed/incomplete bundles remain diagnostic
evidence and may fail replay validation.

Metrics include numerator, denominator and value (`null` when not applicable):

| Metric | Definition | Gate |
| --- | --- | --- |
| `loop_pass_rate` | Cases meeting expected terminal and scenario assertions / fixed catalog | 100% |
| `observation_accuracy` | Verified model observations / required observations | 100% |
| `recovery_rate` | Passing required recovery cases / required recovery cases | 100% |
| `duplicate_call_rate` | Unexpected repeated actual executions / actual executions | 0% |

Correct refusal and cancellation count as passing scenarios. Recovery absence
does not count as successful recovery. Idempotency cache hits are not executions.
Missing cases, missing evidence, validation failures or insufficient observation
coverage fail the gate. General entrypoint Eval `error_recovery` aggregates are
not substitutes for the loop gate's explicit recovery sample.

CI job `agent-fake-llm-gate` runs these scenarios and the HTTP recovery regression.
The pytest flag `--offline-agent-gate` also blocks network during test setup,
execution and teardown. Artifact `ci-agent-fake-llm-gate` retains JUnit, entrypoint
Eval and loop replay evidence for 14 days, including failed runs. Local pytest
only saves a JUnit report when `--junitxml=...` is supplied. Remote repository
rules must require `repository-quality` to prevent merging failed checks; that
setting is external to this workflow file.
