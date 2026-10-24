"""Test-only database isolation and strict external HTTP doubles."""

from collections import deque
from contextlib import asynccontextmanager
from uuid import uuid4
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel


def validate_postgres_url(value):
    """Fail closed without displaying credentials or attempting a connection."""
    try:
        url = make_url(value)
    except Exception:
        raise pytest.UsageError(
            "TEST_POSTGRES_URL must be a local dedicated *_test database"
        ) from None
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or not url.database
        or not url.database.endswith("_test")
        or url.query
    ):
        raise pytest.UsageError(
            "TEST_POSTGRES_URL must be a local dedicated *_test database without URL options"
        )
    return url


@asynccontextmanager
async def isolated_postgres_engine(url):
    """Create/drop only a UUID schema in an explicitly validated test database."""
    url = validate_postgres_url(url)
    schema = "test_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    engine = None
    created = False
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_async_engine(
            url,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        # Register application tables independently of collection/import order.
        import app.models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        yield engine
    finally:
        try:
            if engine is not None:
                await engine.dispose()
        finally:
            try:
                if created:
                    async with admin.begin() as conn:
                        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            finally:
                await admin.dispose()


class ExternalHTTPDouble:
    """Queue exact method/URL responses; never forward an unexpected request."""

    def __init__(self):
        self.pending: deque[tuple[str, str, Any, int, httpx.RequestError | None]] = (
            deque()
        )
        self.requests = []
        self.transport = httpx.MockTransport(self.handle)

    def respond(self, method, url, *, json=None, status=200, error=None):
        self.pending.append((method.upper(), url, json, status, error))

    def handle(self, request):
        self.requests.append(request)
        if not self.pending:
            raise AssertionError("Unplanned external HTTP request")
        method, url, payload, status, error = self.pending[0]
        if (request.method, str(request.url)) != (method, url):
            raise AssertionError("Unplanned external HTTP method or URL")
        self.pending.popleft()
        if error is not None:
            error.request = request
            raise error
        return httpx.Response(status, json=payload, request=request)
