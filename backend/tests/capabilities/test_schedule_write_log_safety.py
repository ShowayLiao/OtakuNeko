"""Schedule write synchronization logs must not expose provider or SQL details."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.adaptersV2 import bangumi_calendar_to_subject_upsert_list
from app.schemas.bangumi import BangumiCalendar, BangumiCalendarDay, BangumiCalendarItem
from app.services import bangumi_data_sync
from app.services.bangumi_data_sync import BangumiDataSyncService


_PRIVATE_SQL = "synthetic-private-data-sync-sql"
_PRIVATE_HTTP = "synthetic-private-data-sync-http"
_PRIVATE_SUBJECT = "synthetic-private-calendar-subject"


def _assert_private_detail_is_absent(caplog, logger):
    records = [record for record in caplog.records if record.name == logger.name]
    assert records
    assert all(
        _PRIVATE_SQL not in repr(record.__dict__)
        and _PRIVATE_HTTP not in repr(record.__dict__)
        and _PRIVATE_SUBJECT not in repr(record.__dict__)
        and record.exc_info is None
        for record in records
    )
    return records


@pytest.mark.asyncio
async def test_air_time_batch_logs_error_type_without_database_error(caplog):
    class BrokenSession:
        async def execute(self, *args, **kwargs):
            raise SQLAlchemyError(_PRIVATE_SQL)

    logger = bangumi_data_sync.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            result = await BangumiDataSyncService.get_air_time_batch(
                cast(Any, BrokenSession()), [101]
            )
    finally:
        logger.removeHandler(caplog.handler)

    assert result == {}
    records = _assert_private_detail_is_absent(caplog, logger)
    assert any(
        record.action == "sync_bangumi_schedule"
        and record.error_type == "SQLAlchemyError"
        for record in records
    )


@pytest.mark.asyncio
async def test_recent_data_sync_logs_http_error_type_without_provider_error(
    monkeypatch, caplog
):
    request = httpx.Request("GET", "https://example.test/calendar.json")

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            raise httpx.RequestError(_PRIVATE_HTTP, request=request)

    async def no_wait(_delay):
        return None

    monkeypatch.setattr(BangumiDataSyncService, "DATA_SOURCES", (str(request.url),))
    monkeypatch.setattr(
        bangumi_data_sync.httpx, "AsyncClient", lambda **kwargs: FailingClient()
    )
    monkeypatch.setattr(asyncio, "sleep", no_wait)

    logger = bangumi_data_sync.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            with pytest.raises(Exception):
                await BangumiDataSyncService.fetch_and_sync_recent_data(
                    db=type("BrokenSession", (), {"rollback": no_wait})()
                )
    finally:
        logger.removeHandler(caplog.handler)

    records = _assert_private_detail_is_absent(caplog, logger)
    assert any(
        record.action == "sync_bangumi_schedule" and record.error_type == "RequestError"
        for record in records
    )


def test_calendar_adapter_does_not_log_full_invalid_subject_payload(caplog):
    calendar = BangumiCalendar(
        root=[
            BangumiCalendarDay(
                weekday={"id": "synthetic-private-calendar-subject"},
                items=[
                    BangumiCalendarItem.model_validate(
                        {"id": 101, "name": _PRIVATE_SUBJECT}
                    )
                ],
            )
        ]
    )
    logger = logging.getLogger("app.schemas.adaptersV2")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger=logger.name):
            result = bangumi_calendar_to_subject_upsert_list(calendar)
    finally:
        logger.removeHandler(caplog.handler)

    assert result.items == []
    records = _assert_private_detail_is_absent(caplog, logger)
    assert any(
        record.action == "sync_bangumi_schedule"
        and record.error_type == "ValidationError"
        for record in records
    )
