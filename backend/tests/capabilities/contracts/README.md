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

Anime, Subjects, Recommendation, and Stats owner-specific scenarios remain
mandatory alongside the six base scenarios. Registry and fixture inventory
determine the global expected and passed counts; no fixed total is used.

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
