# Agent evaluations

Run the deterministic PR gate from `backend/`:

```bash
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
```

The command executes fixtures through `AgentRuntime`, requires no network or
secrets, writes a machine-readable report under `.runtime/evaluation/`, and
returns non-zero when a configured threshold or baseline regresses.

`full.yaml` explicitly loads the production `ChatWorkflow` target and an
OpenAI-compatible Judge through configured factories. It requires provider
credentials, runs sequentially within the configured concurrency ceiling, and
enforces both a per-call cost reservation and a total Judge budget. Provider
responses and credentials are never copied into reports.

Published datasets, baselines, and threshold configuration are append-only.
Create a new version instead of overwriting an approved version.
