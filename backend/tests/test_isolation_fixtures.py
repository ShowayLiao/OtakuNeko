"""Regression contracts for shared test isolation fixtures."""

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models import User


async def _users(session):
    return (await session.exec(select(User))).all()


@pytest.mark.parametrize("case", ["first", "second"])
async def test_committed_rows_do_not_cross_test_boundary(db_session, case):
    assert await _users(db_session) == []
    db_session.add(User(id=731, username="same-id", hashed_password="test-only"))
    await db_session.commit()
    assert len(await _users(db_session)) == 1


async def test_sqlite_engine_sessions_share_only_their_test_database(sqlite_engine):
    factory = async_sessionmaker(sqlite_engine, class_=AsyncSession)
    async with factory() as first:
        first.add(User(id=732, username="cross-session", hashed_password="test-only"))
        await first.commit()
    async with factory() as second:
        assert len(await _users(second)) == 1


@pytest.mark.parametrize("case", ["first", "second"])
async def test_cache_does_not_cross_tests(initialized_cache, case):
    from fastapi_cache import FastAPICache

    backend = FastAPICache.get_backend()
    assert await backend.get("isolation-probe") is None
    await backend.set("isolation-probe", b"data", expire=60)


@pytest.mark.parametrize("case", ["first", "second"])
async def test_api_auth_and_committed_data_are_isolated(
    api_app, api_client, db_session, case
):
    from app.api.deps import get_current_user

    user = User(id=733, username="api-fixture", hashed_password="test-only")
    assert await _users(db_session) == []
    db_session.add(user)
    await db_session.commit()
    assert (await api_client.get("/api/v1/users/me")).status_code == 401
    api_app.dependency_overrides[get_current_user] = lambda: user
    response = await api_client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["id"] == 733


async def test_external_double_runs_real_bangumi_client(external_http):
    from app.services.bangumi_client import BangumiClient

    external_http.respond("GET", "https://api.bgm.tv/v0/subjects/42", json={"id": 42})
    assert await BangumiClient().get_subject_raw(42) == {"id": 42}
    assert len(external_http.requests) == 1


async def test_external_double_propagates_timeout(external_http):
    from app.services.bangumi_client import BangumiClient

    external_http.respond(
        "GET",
        "https://api.bgm.tv/v0/subjects/42",
        error=httpx.ReadTimeout("fake timeout"),
    )
    with pytest.raises(httpx.ReadTimeout):
        await BangumiClient().get_subject_raw(42)


async def test_external_double_rejects_unplanned_requests(external_http):
    with pytest.raises(AssertionError, match="Unplanned"):
        async with httpx.AsyncClient() as client:
            await client.get("https://unexpected.invalid")


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:///local.db",
        "postgresql+asyncpg://test:test@localhost/otakuneko",
        "postgresql+asyncpg://test:test@production.example/otakuneko_test",
        "postgresql+asyncpg://test:test@localhost/otakuneko_test?options=unsafe",
    ],
)
def test_postgres_fixture_rejects_non_test_targets(url):
    from tests.isolation_support import validate_postgres_url

    with pytest.raises(pytest.UsageError):
        validate_postgres_url(url)


@pytest.mark.postgres
@pytest.mark.parametrize("case", ["first", "second"])
async def test_postgres_commits_are_isolated(postgres_session, case):
    assert await _users(postgres_session) == []
    postgres_session.add(
        User(id=734, username="pg-isolation", hashed_password="test-only")
    )
    await postgres_session.commit()
    assert len(await _users(postgres_session)) == 1


@pytest.mark.postgres
async def test_postgres_schema_is_removed_after_context():
    import os
    from tests.isolation_support import isolated_postgres_engine, validate_postgres_url
    from sqlalchemy.ext.asyncio import create_async_engine

    url = validate_postgres_url(os.environ["TEST_POSTGRES_URL"])
    async with isolated_postgres_engine(url) as engine:
        async with engine.connect() as conn:
            schema = (await conn.execute(text("select current_schema()"))).scalar_one()
            assert schema.startswith("test_")
    admin = create_async_engine(url)
    try:
        async with admin.connect() as conn:
            assert (
                await conn.execute(
                    text("select count(*) from pg_namespace where nspname = :schema"),
                    {"schema": schema},
                )
            ).scalar_one() == 0
    finally:
        await admin.dispose()


async def test_external_double_propagates_http_failure(external_http):
    from app.services.bangumi_client import BangumiClient

    external_http.respond(
        "GET",
        "https://api.bgm.tv/v0/subjects/42",
        status=503,
        json={"error": "fake unavailable"},
    )
    with pytest.raises(httpx.HTTPStatusError) as error:
        await BangumiClient().get_subject_raw(42)
    assert error.value.response.status_code == 503


@pytest.mark.postgres
async def test_postgres_schema_cleanup_survives_test_failure():
    import os
    from tests.isolation_support import isolated_postgres_engine, validate_postgres_url
    from sqlalchemy.ext.asyncio import create_async_engine

    url = validate_postgres_url(os.environ["TEST_POSTGRES_URL"])
    with pytest.raises(RuntimeError, match="simulated failure"):
        async with isolated_postgres_engine(url) as engine:
            async with engine.begin() as conn:
                schema = (
                    await conn.execute(text("select current_schema()"))
                ).scalar_one()
                await conn.execute(text("create table committed_probe (id integer)"))
            raise RuntimeError("simulated failure")
    admin = create_async_engine(url)
    try:
        async with admin.connect() as conn:
            assert (
                await conn.execute(
                    text("select count(*) from pg_namespace where nspname = :schema"),
                    {"schema": schema},
                )
            ).scalar_one() == 0
    finally:
        await admin.dispose()


@pytest.mark.postgres
@pytest.mark.parametrize("case", ["first", "second"])
async def test_postgres_api_reads_committed_data(
    postgres_session, api_app, api_client, case
):
    from app.api.deps import get_current_user
    from app.db.database import get_session

    assert await _users(postgres_session) == []
    user = User(id=735, username="pg-api", hashed_password="test-only")
    postgres_session.add(user)
    await postgres_session.commit()

    async def override_session():
        yield postgres_session

    api_app.dependency_overrides[get_session] = override_session
    assert (await api_client.get("/api/v1/users/me")).status_code == 401
    api_app.dependency_overrides[get_current_user] = lambda: user
    response = await api_client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["username"] == "pg-api"


def test_postgres_opt_in_missing_url_fails_before_collection(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = dict(os.environ)
    env.pop("TEST_POSTGRES_URL", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--run-postgres",
            "--collect-only",
            "tests/test_matrix_classification.py",
            "-q",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 4
    assert "local dedicated *_test database" in result.stderr


async def test_api_and_external_double_keep_separate_transports(
    external_http, api_client
):
    from app.services.bangumi_client import BangumiClient

    assert (await api_client.get("/api/v1/users/me")).status_code == 401
    external_http.respond("GET", "https://api.bgm.tv/v0/subjects/42", json={"id": 42})
    assert await BangumiClient().get_subject_raw(42) == {"id": 42}
    assert [request.url.host for request in external_http.requests] == ["api.bgm.tv"]
