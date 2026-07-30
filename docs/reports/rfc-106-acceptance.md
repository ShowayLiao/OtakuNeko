# OtakuNeko V3 RFC-106 Acceptance Evidence

**Verified:** 2026-07-30

**Branch:** `feature-harness`

## Verification results

The following commands were run from `backend/` with `DEBUG=false`:

```bash
uv run pytest tests -q
uv run ruff check app tests
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
```

Results:

| Check | Result |
|---|---|
| Full backend regression | 455 passed, 65 warnings |
| Architecture boundary tests | 7 passed |
| Runtime acceptance scenarios | 4 passed |
| Ruff | All checks passed |
| Fast evaluation | 9/9 passed, 100% |

The warnings are existing Pydantic V2 configuration and SQLModel
`session.execute()` deprecation warnings. They do not fail the current test
policy, but should be removed before the corresponding upstream APIs are
upgraded.

## Evidence matrix

| RFC-106 criterion | Evidence |
|---|---|
| Multiple agents cooperate | Agent routing, specialist, handoff, and registry tests under `tests/agents/` |
| Memory improves over time | Durable SQL repository, typed memory, retention, isolation, deletion, and restart tests under `tests/memory/` |
| Capabilities are modular | Capability registry and MCP exposure/dispatch tests under `tests/capabilities/` and `tests/mcp/` |
| Tasks run proactively | Scheduler, lease, policy, migration, and execution tests under `tests/proactive/` |
| AI-assisted evolution is sustainable | Deterministic evaluation framework and 9-case fast dataset |

Runtime-level acceptance scenarios additionally verify successful and failed
execution lifecycle traces, trace user isolation, and streaming lifecycle
traces in `tests/acceptance/test_end_to_end.py`.

## Dependency boundary status

`tests/architecture/test_dependency_direction.py` recursively parses Python
source without importing the application. This keeps the check independent of
runtime configuration and optional dependencies.

The following boundaries are enforced:

- agents do not import services directly;
- capabilities do not import API modules;
- harness modules do not import API modules;
- new direct API-to-service or API-to-agent imports are rejected.

The legacy API layer still contains a documented allowlist of direct service
imports, plus direct agent assembly in the agent endpoint. Removing entries
from that allowlist is permitted; expanding it is not. Therefore the current
guard prevents dependency debt from growing, but does not claim that the legacy
API layer has already been fully migrated through the harness.

## Migration history

| Revision | Description |
|---|---|
| `e567b858f91b` | Add collection and subject indexes |
| `2739cf766725` | Add `source` and `source_id` to Subject |
| `bbd93366421b` | Change `bangumi_id` type and add User sign |
| `4b578619fc54` | Add `agent_memory` table |
| `bf40dc9e653e` | Add proactive task definition and run tables |
| `5ae716ad749d` | Add agent trace and trace event tables |

## Deferred items

- migrate remaining legacy API service imports through the intended boundary;
- replace Pydantic class-based configuration before Pydantic V3;
- replace deprecated SQLModel `session.execute()` usage;
- implement AnimeAgent and CompanionAgent specialists;
- add frontend trace visualization and richer distributed tracing.
