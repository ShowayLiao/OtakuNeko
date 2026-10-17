# Backend test matrix

The test suite has one default tier and several overlapping execution
dimensions. Tests are marked `unit` or `integration`; `db`, `api`, and
`postgres` describe additional requirements and may overlap either tier.

The matrix plugin applies these defaults during collection:

- Tests under `api/`, `acceptance/`, `repositories/`, `services/`, or
  `proactive/` default to `integration`; all other tests default to `unit`.
- A test requesting `db_session`, `sqlite_engine`, `postgres_engine`,
  `postgres_session`, or `temp_db_path` is promoted to `integration` and gets
  the `db` marker. PostgreSQL fixtures also get `postgres`.
- An explicit `db` or `postgres` marker promotes a test to `integration` and
  `postgres` also implies `db`; an explicit `unit` marker still takes
  precedence for the tier.
- Tests under `api/` or requesting `api_app` or `api_client` are marked `api`
  and are promoted to `integration`.
- Tests requesting `external_http` are promoted to `integration` because they
  exercise a service boundary through a controlled HTTP double.
- An explicit `unit` or `integration` marker takes precedence over the tier
  heuristic. The `db` and `api` dimensions remain independent of that choice.

These directory and fixture rules are intentionally conservative heuristics;
use explicit markers when a test's execution requirements are clearer than its
location or fixture closure.

The normal software gate uses SQLite and does not run PostgreSQL tests:

```text
uv run --directory backend pytest
```

PostgreSQL tests are opt-in and run against a disposable dedicated database:

```text
TEST_POSTGRES_URL=postgresql+asyncpg://... uv run --directory backend pytest --run-postgres -m postgres
```

When `--run-postgres` is enabled, the test harness requires
`TEST_POSTGRES_URL`; a missing URL is a configuration failure rather than an
implicit fallback. The CI PostgreSQL job provides a PostgreSQL 16 service and
test-only credentials. The URL must use a local loopback host, an `asyncpg`
driver, a database ending in `_test`, and no query options.

The root test conftest supplies isolated `sqlite_engine`/`db_session` and
`postgres_engine`/`postgres_session` fixtures, real ASGI `api_app`/`api_client`
fixtures, and a strict `external_http` double. Database fixtures create and
dispose their engines per test; PostgreSQL uses a temporary schema. The API
fixture verifies route behavior through ASGI transport but does not run the
application lifespan.

To detect order-dependent state leakage, run the same matrix in reverse
collection order:

```text
uv run --directory backend pytest --reverse-test-order
```
