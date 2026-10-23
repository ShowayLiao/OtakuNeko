# Public Capability contracts

The production `build_capability_registry()` is the inventory authority. Every
descriptor, including writes and its declared version, must have an explicit
`Case` in `fixtures_core.py` or `fixtures_external.py`. The action set is not a
fixed count and does not use the default read-only discovery catalog.

From the repository root:

```sh
uv run --directory backend pytest tests/capabilities/contracts -q
uv run --directory backend pytest -p tests.capabilities.contracts.plugin tests/capabilities/contracts --capability-contract-gate --capability-contract-report=.runtime/capability-contracts/coverage.json -q
```

CI enables the second command's plugin and options on its existing Harness
regression command. The gate requires actual scenario assertions and successful
setup, call, and teardown. Missing actions/versions, missing required paths,
deselected scenarios, skips, and xfails cannot satisfy it. A focused local run
can omit the gate option. Evidence is uploaded by the Harness job even on failure.
Remote branch protection remains a repository administrator setting.

## Full CI summary gate

The report is schema version `v2`. In addition to the coverage arithmetic it
contains the compact production Registry inventory, the executed
action/scenario-to-test mapping, per-scenario failure reasons (stage and
exception type, never raw messages), and a static audit of literal direct
capability calls in `backend/app`.

Both the full `software` job and the focused `harness` job enable the plugin and
run the following from `backend/` (the CI working directory, or after
`cd backend`):

```sh
uv run --locked python scripts/capability_ci_summary.py \
  --report .runtime/capability-contracts/<gate-report>.json \
  --junit .runtime/junit/<job>.xml \
  --output .runtime/capability-ci/<job>-summary.json \
  --markdown .runtime/capability-ci/<job>-summary.md \
  --step-summary "$GITHUB_STEP_SUMMARY"
```

The summary step runs with `if: always()`, so a collection failure or missing
report still fails the job instead of silently skipping the gate. It exits
non-zero when any required observation is missing, a contract test fails, a
literal direct call names an unregistered action, a contract marker names an
unregistered action/version, JUnit reports failing tests, or the report is
inconsistent. `repository-quality` continues to require both jobs, so these
checks block a pull request through the aggregate job.

The static audit resolves identifier-shaped literal action names passed
positionally or as `action=` to `*.execute(...)` except on exact
database/session/connection/cursor/engine/conn handles, plus
`action`/`public_action` literals in
`._execute_capability(..., public_action=...)`. `execute` literals must be
internal action names and `public_action` literals must be public names. SQL
text with spaces and dynamic action variables are not guessed; the Dispatcher
remains the runtime boundary for those.

To add or change an action:

1. Add a literal `(public_name, version)` case with valid arguments, a nonempty
   business-output subset assertion, and an async dependency preparation function.
2. Isolate dependencies at the imported domain/provider boundary. Never replace
   the Capability implementation for the positive example. Check the supplied
   trusted principal/session, and record calls. Use nonempty nested inputs so
   nested required fields are tested. Real provider/qB/network calls are forbidden.
3. Review the descriptor's executable schema and metadata. Deliberately update
   its SHA-256 fingerprint in `snapshots.py` using `catalog.fingerprint`; there is
   no automatic CI snapshot update. A description edit does not change the hash.
4. Run the full contract gate and relevant backend regressions. Branching input
   schemas fail closed during required-field traversal; extend the framework with
   explicit branch fixtures before introducing one. Output alternatives are
   validated by the normalizer; calendar output supports its root list and the
   existing `days` object compatibility shape.

Positive examples use the shared production Runtime composition, Dispatcher,
Policy, CapabilityAdapter, ResultNormalizer, and temporary SQLite idempotency
store. Each write needs trusted approval; replay with a new decision ID must not
call its dependencies again. Dependencies return synthetic business data, so
this suite does not replace domain service or live provider integration tests.

Error, timeout, exception isolation, and unsafe-output cases are explicitly
**boundary fault injection**. The timeout blocker is entered before arming the
real Dispatcher deadline, so database admission time cannot masquerade as a
cancelled Capability. The serialization case first executes the real action and
round-trips the result, then probes the normalizer with unsupported objects/NaN.
It does not assert that an arbitrary raw write result can be stored in SQL.

The report separates open output schemas from declared output constraints.
Fixture business assertions do not make an open production schema strongly typed.
Required coverage counts concrete fixture paths, including array element indexes;
actions declaring no required input fields have no fabricated required-field case.

Anime certification adds six mandatory scenarios per production Registry action
owned by `anime`: `anime_error`, `anime_timeout`, `anime_isolation`,
`anime_serialization`, `anime_authorization`, and `anime_dispatcher`.
These use the real action handlers and replace imported Bangumi dependencies;
the timeout tests leave Dispatcher controls intact. Omitting their test files,
filtering them, or skipping a required scenario fails the same execution gate.
HTTP/JWT integration is additionally exercised by
`tests/api/test_anime_certification.py`. Public Anime lookups permit anonymous
execution; linked-account lookup requires the authenticated user's binding.

Subjects certification adds six mandatory scenarios per production Registry
action owned by `subjects`: `subjects_error`, `subjects_timeout`,
`subjects_isolation`, `subjects_serialization`, `subjects_authorization`, and
`subjects_dispatcher`. `tests/capabilities/contracts/test_subjects_handlers.py`
uses the real registered Subjects handlers and isolates imported service or
repository dependencies. Omitting that file, filtering it, or skipping a
required scenario fails the same execution gate. This certifies handler
behavior through the Runtime Dispatcher; service behavior and SQL persistence
remain outside this certification's evidence boundary and require their own
service and database tests.

Recommendation and Stats certification adds six owner-specific scenarios to
every public action in the production Registry owned by `recommendation` or
`stats`: `recommendation_error`, `recommendation_timeout`,
`recommendation_isolation`, `recommendation_serialization`,
`recommendation_authorization`, `recommendation_dispatcher`, and the matching
`stats_*` scenarios. `tests/capabilities/contracts/test_profile_stats_handlers.py`
executes the real registered handlers through the shared Runtime Dispatcher,
injecting isolated service/computation dependencies at their imported
boundaries. Omitting that file, filtering its scenarios, or skipping a required
observation fails the same execution gate. This handler certification does not
cover real HTTP/JWT requests or SQL behavior; those are separate evidence in
`tests/api/test_profile_stats_certification.py` and
`tests/capabilities/test_recommendation_stats_semantics.py`.

Anime, Subjects, Recommendation, Stats, Collections read, Schedule read, and
Media read owner-specific scenarios remain mandatory alongside the six base
scenarios. Registry and fixture inventory determine the global expected and
passed counts; no fixed total is used.

Collections read certification adds six mandatory scenarios to each public
action owned by `collections` only when its production descriptor has
`is_side_effect == false`: `collections_read_error`,
`collections_read_timeout`, `collections_read_isolation`,
`collections_read_serialization`, `collections_read_authorization`, and
`collections_read_dispatcher`. The current Registry has three such actions;
collection writes are not certified by this matrix.
`tests/capabilities/contracts/test_collections_read_handlers.py` exercises the
registered read handlers through the shared Runtime Dispatcher with imported
dependencies isolated. HTTP/API and Service/SQL behavior are covered separately
by `tests/api/test_collections_read_certification.py` and
`tests/capabilities/test_collections_read_semantics.py`.

Schedule read certification adds six mandatory scenarios to each public action
owned by `schedule` only when its production descriptor has
`is_side_effect == false`: `schedule_read_error`, `schedule_read_timeout`,
`schedule_read_isolation`, `schedule_read_serialization`,
`schedule_read_authorization`, and `schedule_read_dispatcher`. The current
read allowlist is frozen to `list_schedules`, `list_schedules_by_day`, and
`list_unified_schedules`; schedule writes are outside this matrix.
`tests/capabilities/contracts/test_schedule_read_handlers.py` exercises the
registered read handlers through the shared Runtime Dispatcher with imported
dependencies isolated. Omitting that file, filtering its timeout observation,
or skipping a required observation fails the execution gate. HTTP/API and
Service/SQL behavior are covered separately by
`tests/api/test_schedule_contract.py` and
`tests/capabilities/test_schedule_read_semantics.py`.

Media read certification adds six mandatory scenarios to each public action
owned by `media` only when its production descriptor has
`is_side_effect == false`: `media_read_error`, `media_read_timeout`,
`media_read_isolation`, `media_read_serialization`,
`media_read_authorization`, and `media_read_dispatcher`. The frozen read
allowlist is `library_status`, `list_rss_feeds`, and `list_rss_rules`; the five
Media write actions are outside this matrix. `library_status` reports local
configuration and does not test qB connectivity. The matrix covers the
registered handlers through the shared Runtime Dispatcher, with external qB
SDK/client access isolated. It does not certify REST routing, service/SQL
behavior, live qB connectivity, or Media writes. Omitting
`tests/capabilities/contracts/test_media_read_handlers.py`, filtering its
timeout scenarios, or skipping a required observation fails the gate.

Collections write certification adds eight mandatory scenarios to every public
action owned by `collections` whose production descriptor has
`is_side_effect == true`: `collections_write_error`,
`collections_write_timeout`, `collections_write_isolation`,
`collections_write_serialization`, `collections_write_authorization`,
`collections_write_dispatcher`, `collections_write_approval`, and
`collections_write_idempotency`. The current Registry has eight such actions,
so this matrix requires 64 additional observations. The six read scenarios remain
separate and unchanged.

`tests/capabilities/contracts/test_collections_write_handlers.py` executes the
real registered write handlers through the shared Runtime Dispatcher and
isolates only imported handler dependencies. Omitting the file, filtering its
timeout scenario, or skipping a required observation fails the gate. Actual
HTTP/JWT behavior and SQL semantics are certified separately by
`tests/api/test_collections_write_certification.py` and
`tests/capabilities/test_collections_write_semantics.py`.

Schedule write certification adds nine mandatory scenarios to each public
action owned by `schedule` whose production descriptor has
`is_side_effect == true`: `schedule_write_error`, `schedule_write_timeout`,
`schedule_write_isolation`, `schedule_write_serialization`,
`schedule_write_authorization`, `schedule_write_dispatcher`,
`schedule_write_approval`, `schedule_write_idempotency`, and
`schedule_write_recovery`. The frozen write inventory has six actions, so this
matrix requires 54 additional observations; the six Schedule read scenarios
remain separate and unchanged.
`tests/capabilities/contracts/test_schedule_write_handlers.py` executes the
registered write handlers through the shared Runtime Dispatcher and isolates
only imported handler dependencies. The recovery scenario rebuilds
Runtime/Adapter/Session from durable state. Omitting the handler file, filtering
its timeout or recovery scenario, or skipping an observation fails the gate.
Process kill/restore, HTTP/JWT behavior, and SQL semantics are certified
separately by `tests/acceptance/test_schedule_write_kill_restore.py`,
`tests/api/test_schedule_write_certification.py`, and
`tests/capabilities/test_schedule_write_semantics.py`.

Media write certification adds nine mandatory scenarios to each public action
owned by `media` whose production descriptor has `is_side_effect == true`:
`media_write_error`, `media_write_timeout`, `media_write_isolation`,
`media_write_serialization`, `media_write_authorization`,
`media_write_dispatcher`, `media_write_approval`,
`media_write_idempotency`, and `media_write_recovery`. The current Registry has
five Media write actions, so this matrix requires 45 additional observations;
the six Media read scenarios remain separate and unchanged.
`tests/capabilities/contracts/test_media_write_handlers.py` exercises the
registered write handlers through the shared Runtime Dispatcher. Omitting the
handler file, filtering its timeout or recovery scenario, or skipping a required
observation fails the same execution gate. HTTP/JWT behavior and service/SQL
semantics are certified separately by
`tests/api/test_media_write_certification.py`,
`tests/capabilities/test_media_write_semantics.py`, and
`tests/services/test_qb_service.py`.

System certification adds six mandatory scenarios to the single production
Registry action owned by `system`: `system_error`, `system_timeout`,
`system_isolation`, `system_serialization`, `system_authorization`, and
`system_dispatcher`. The current action is `get_current_time@v1`; it is declared
public and identity-free (`requires_auth == false`), returns no user or tenant
data, and is not exposed over MCP. `tests/capabilities/contracts/test_system_handlers.py`
executes the real registered handler through the shared Runtime Dispatcher. It
replaces the local clock for deterministic success and clock-failure injection,
wraps `execute` for argument observation in the authorization and dispatcher
scenarios, replaces it with an infinite blocker for the timeout probe and with
a raiser for the isolation failure half, and replaces it with unsafe output for
the serialization boundary probe; `Dispatcher._run_with_controls` is armed only
for the timeout probe. Omitting that file, filtering a scenario, or skipping a
required observation fails the gate. HTTP/JWT identity boundaries, structured
error envelopes, and exception containment are certified separately by
`tests/api/test_system_certification.py`.
