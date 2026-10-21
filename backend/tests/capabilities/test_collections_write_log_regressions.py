"""Private import data and post-commit cache diagnostics stay out of logs."""

from copy import deepcopy
import logging
from typing import Any

from fastapi_cache import FastAPICache
import pytest

from app.capabilities import collections as boundary
from app.repositories import collection_repo, subject_repo
from app.schemas import adaptersV2 as adapters
from app.services import bangumi_service, collection_service, subject_service
from tests.api import test_collections_write_certification as support


@pytest.mark.parametrize(
    "case",
    [
        "subject_validation",
        "subject_type",
        "collection_validation",
        "collection_time",
        "collection_status",
        "douban_type",
    ],
)
def test_import_conversion_warning_never_logs_private_payload(case, caplog):
    item: dict[str, Any] = {
        "subject_id": 704,
        "type": 3,
        "rate": 8,
        "comment": "synthetic-private-comment",
        "subject": {"id": 704, "type": 2, "name": "Synthetic subject"},
    }
    if case == "subject_validation":
        item["subject"]["name"] = {"private": "synthetic-private-title"}
    elif case == "subject_type":
        item["subject"]["type"] = "synthetic-private-type"
    elif case == "collection_validation":
        item["rate"] = "synthetic-private-invalid-rate"
    elif case == "collection_time":
        item["updated_at"] = "synthetic-private-invalid-date"
    elif case == "collection_status":
        item["type"] = "synthetic-private-collection-type"
    with caplog.at_level(logging.WARNING, logger=adapters.logger.name):
        if case == "douban_type":
            converted = adapters.douban_to_bangumi_list(
                {
                    "interest": [
                        {
                            "interest": {
                                "status": "done",
                                "subject": {
                                    "id": "704",
                                    "type": "synthetic-private-douban-type",
                                    "title": "Synthetic title",
                                },
                            }
                        }
                    ]
                }
            )
            assert len(converted["data"]) == 1
        elif case.startswith("subject"):
            subjects_result = adapters.bangumi_subject_to_subjectlist({"data": [item]})
            assert subjects_result.total == (1 if case == "subject_type" else 0)
        else:
            collections_result = adapters.bangumi_collection_to_collectionlist(
                {"data": [item]}, 7
            )
            assert collections_result.total == (
                1 if case in {"collection_time", "collection_status"} else 0
            )
    records = [
        record for record in caplog.records if record.name == adapters.logger.name
    ]
    assert records
    assert all(
        "synthetic-private" not in repr(record.__dict__) and record.exc_info is None
        for record in records
    )


@pytest.mark.asyncio
async def test_real_bangumi_write_cache_failure_is_safe_success(
    db_session, initialized_cache, monkeypatch, caplog
):
    owner, foreign = await support._seed(db_session)
    assert owner.id is not None and foreign.id is not None
    calls, _, response_slot = support._install_service_counters(
        "sync_bangumi_collections", monkeypatch
    )
    arguments = deepcopy(support._arguments("sync_bangumi_collections", "approved"))
    response_slot["value"] = arguments.pop("_synthetic_bangumi_response")

    async def fail_clear(*args, **kwargs):
        raise RuntimeError("synthetic-private-cache-diagnostic")

    monkeypatch.setattr(FastAPICache, "clear", fail_clear)
    loggers = (
        boundary.logger,
        bangumi_service.logger,
        collection_service.logger,
        subject_service.logger,
        collection_repo.logger,
        subject_repo.logger,
    )
    for logger in loggers:
        logger.addHandler(caplog.handler)
    before = await support._business_snapshot(db_session)
    try:
        with caplog.at_level(logging.WARNING):
            result = await boundary.CollectionCapability().execute(
                "sync_bangumi_collections",
                db=db_session,
                user_id=owner.id,
                user=owner,
                **arguments,
            )
    finally:
        for logger in loggers:
            logger.removeHandler(caplog.handler)
    assert result["success"] is True and result["processed_count"] == 2
    assert calls == ["sync_bangumi_collections"]
    support._assert_business_write(
        "sync_bangumi_collections",
        "approved",
        owner.id,
        foreign.id,
        before,
        await support._business_snapshot(db_session),
    )
    records = [
        record
        for record in caplog.records
        if record.name in {logger.name for logger in loggers}
    ]
    assert records
    assert all(
        "synthetic-private" not in repr(record.__dict__) and record.exc_info is None
        for record in records
    )
