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
