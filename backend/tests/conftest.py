"""Shared backend test isolation: no developer DB or provider configuration."""

import asyncio
import os
import tempfile
from uuid import uuid4

import httpx
import pytest

# Must run before importing any application singleton. Explicit values override
# the developer .env and host environment only in this pytest process.
_TEST_DATA = tempfile.TemporaryDirectory(prefix="otakuneko_tests_")
os.environ.update(
    {
        "DEBUG": "false",
        "DEPLOY_MODE": "local",
        "SQLITE_FILE": ":memory:",
        "CHECKPOINT_DB_PATH": os.path.join(_TEST_DATA.name, "checkpoints.db"),
        "JWT_SECRET_KEY": uuid4().hex + uuid4().hex,
        "OPENAI_API_KEY": "",
        "ENABLE_QB_PROXY": "false",
        "ENABLE_PROACTIVE_SCHEDULER": "false",
        "PROVIDER_RESOLVE_DNS": "false",
        "HARNESS_CHECKPOINT_ADAPTER": "sqlite",
        "HARNESS_CHECKPOINT_SINGLE_WORKER": "true",
        "HARNESS_WORKER_COUNT": "1",
    }
)

from fastapi_cache import FastAPICache  # noqa: E402
from fastapi_cache.backends.inmemory import InMemoryBackend  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402
from tests.isolation_support import (  # noqa: E402
    ExternalHTTPDouble,
    isolated_postgres_engine,
    validate_postgres_url,
)

pytest_plugins = ["tests.matrix_plugin"]


def pytest_addoption(parser):
    parser.addoption(
        "--run-postgres",
        action="store_true",
        help="Enable local dedicated PostgreSQL test database",
    )
    parser.addoption(
        "--reverse-test-order",
        action="store_true",
        help="Reverse collected order to detect state pollution",
    )


def pytest_configure(config):
    if config.getoption("--run-postgres"):
        validate_postgres_url(os.environ.get("TEST_POSTGRES_URL", ""))


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-postgres"):
        skip = pytest.mark.skip(
            reason="PostgreSQL requires --run-postgres and local TEST_POSTGRES_URL"
        )
        for item in items:
            if item.get_closest_marker("postgres"):
                item.add_marker(skip)
    if config.getoption("--reverse-test-order"):
        items.reverse()


class TolerantInMemoryBackend(InMemoryBackend):
    """Redis-compatible deletion of a nonexistent key, with per-instance storage."""

    def __init__(self):
        self._store = {}
        self._lock = asyncio.Lock()

    async def clear(self, namespace=None, key=None):
        if key is not None:
            return int(self._store.pop(key, None) is not None)
        if not namespace:
            count = len(self._store)
            self._store.clear()
            return count
        return await super().clear(namespace=namespace)


@pytest.fixture(autouse=True)
def isolated_cache_state(monkeypatch):
    # FastAPICache.reset() does not clear InMemoryBackend's class-level store.
    FastAPICache.reset()
    monkeypatch.setattr(InMemoryBackend, "_store", {})
    monkeypatch.setattr(InMemoryBackend, "_lock", asyncio.Lock())
    try:
        yield
    finally:
        InMemoryBackend._store.clear()
        FastAPICache.reset()


@pytest.fixture
def initialized_cache(isolated_cache_state):
    backend = TolerantInMemoryBackend()
    FastAPICache.init(backend)
    try:
        yield backend
    finally:
        backend._store.clear()
        FastAPICache.reset()


@pytest.fixture
def temp_db_path(tmp_path):
    # tmp_path cleanup owns the DB plus WAL/SHM sidecars; do not swallow errors.
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
async def sqlite_engine():
    import app.models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(sqlite_engine):
    factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest.fixture
async def postgres_engine(pytestconfig):
    if not pytestconfig.getoption("--run-postgres"):
        pytest.skip("PostgreSQL requires --run-postgres")
    url = validate_postgres_url(os.environ.get("TEST_POSTGRES_URL", ""))
    async with isolated_postgres_engine(url) as engine:
        yield engine


@pytest.fixture
async def postgres_session(postgres_engine):
    factory = async_sessionmaker(
        postgres_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest.fixture
def api_app(db_session, initialized_cache):
    from fastapi import FastAPI
    from app.api import api_router
    from app.db.database import get_session

    app = FastAPI()
    app.include_router(api_router)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def api_client(api_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def external_http(monkeypatch):
    double = ExternalHTTPDouble()
    # Patch the constructor method, preserving AsyncClient's class identity:
    # provider SDKs subclass it during import. Local ASGI must keep its transport.
    original_init = httpx.AsyncClient.__init__

    def client_init(client, *args, **kwargs):
        if not isinstance(kwargs.get("transport"), httpx.ASGITransport):
            kwargs["transport"] = double.transport
        original_init(client, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", client_init)
    yield double
    assert not double.pending, "Planned external HTTP responses were not consumed"


def pytest_sessionfinish(session, exitstatus):
    _TEST_DATA.cleanup()
