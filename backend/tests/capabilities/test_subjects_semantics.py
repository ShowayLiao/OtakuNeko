"""Subjects regression through real services; only external I/O is replaced."""

from __future__ import annotations

import json
import logging

import pytest

from app.capabilities.subjects import SubjectCapability
from app.services import subject_service


@pytest.mark.asyncio
async def test_remote_pagination_reaches_bangumi_offset(monkeypatch):
    calls = []

    async def remote(keyword, subject_type, limit, offset):
        calls.append((keyword, subject_type, limit, offset))
        return {"total": 0, "data": []}

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    result = await SubjectCapability().execute(
        "search_remote_subjects", keyword="synthetic", type=2, skip=13, limit=4
    )
    assert result == {"success": True, "total": 0, "subjects": []}
    assert calls == [("synthetic", 2, 4, 13)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "exception",
        "invalid_response",
        "missing_data",
        "wrong_data",
        "wrong_total",
        "invalid_item",
    ],
)
async def test_remote_real_service_failure_is_not_empty_success(monkeypatch, failure):
    async def remote(*args):
        if failure == "exception":
            raise RuntimeError("synthetic-private-upstream-diagnostic")
        return {
            "invalid_response": None,
            "missing_data": {},
            "wrong_data": {"total": 1, "data": {}},
            "wrong_total": {"total": True, "data": []},
            "invalid_item": {"total": 1, "data": [None]},
        }[failure]

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    result = await SubjectCapability().execute("search_remote_subjects", keyword="test")
    assert result["success"] is False
    assert result["error_type"] == "upstream_error"
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("side", ["local", "remote"])
async def test_mixed_failure_is_not_reported_as_complete_success(monkeypatch, side):
    async def local(*args):
        if side == "local":
            raise RuntimeError("synthetic-private-local-diagnostic")
        return subject_service.UnifiedList(total=0, items=[])

    async def remote(*args):
        if side == "remote":
            raise RuntimeError("synthetic-private-remote-diagnostic")
        return {"total": 0, "data": []}

    monkeypatch.setattr(subject_service, "search_subject_by_name", local)
    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    result = await SubjectCapability().execute(
        "search_mixed_subjects", db=object(), user_id=7, keyword="test"
    )
    assert result["success"] is False
    assert result["error_type"] == "upstream_error"
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_value_error_text_is_not_public(monkeypatch):
    async def invalid(*args):
        raise ValueError("synthetic-private-validation-diagnostic")

    monkeypatch.setattr("app.capabilities.subjects.search_subject_by_name", invalid)
    result = await SubjectCapability().execute(
        "search_local_subjects", db=object(), user_id=7
    )
    assert result["success"] is False and result["error_type"] == "invalid_args"
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_strict_service_logs_do_not_include_upstream_diagnostic(
    monkeypatch, caplog
):
    async def remote(*args):
        raise RuntimeError("synthetic-private-upstream-diagnostic")

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    logger = subject_service.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            await SubjectCapability().execute("search_remote_subjects", keyword="test")
    finally:
        logger.removeHandler(caplog.handler)
    records = [entry for entry in caplog.records if entry.name == logger.name]
    assert records
    assert all("synthetic-private" not in repr(entry.__dict__) for entry in records)


def test_all_subjects_success_schemas_are_executable():
    from app.harness.normalizer import ResultNormalizer

    normalizer = ResultNormalizer()
    for descriptor in SubjectCapability().actions():
        assert descriptor.output_schema.get("required"), descriptor.name
        normalized = normalizer.normalize(
            {"success": True},
            descriptor=descriptor,
            run_id="schema-test",
            decision_id="decision",
            invocation_id="invocation",
            trace_id="schema-test",
        )
        assert normalized.status == "failed", descriptor.name


@pytest.mark.asyncio
async def test_non_capability_cloud_and_mixed_keep_default_degradation(
    monkeypatch, db_session
):
    from app.schemas.subject import SubjectSearchBase, SubjectSearchCloud

    async def remote(*args):
        raise RuntimeError("synthetic upstream failure")

    async def local(*args):
        return subject_service.UnifiedList(total=0, items=[])

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    monkeypatch.setattr(subject_service, "search_subject_by_name", local)
    cloud = await subject_service.search_subject_cloud(
        None, SubjectSearchCloud(keyword="test", type=None, user_id=None)
    )
    mixed = await subject_service.search_mixed(
        db_session, SubjectSearchBase(keyword="test", user_id=7, type=None)
    )
    assert cloud.total == 0 and cloud.items == []
    assert mixed.total == 0 and mixed.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize("side", ["local", "remote"])
async def test_strict_mixed_propagates_cancellation(monkeypatch, side):
    import asyncio

    async def local(*args):
        if side == "local":
            raise asyncio.CancelledError()
        return subject_service.UnifiedList(total=0, items=[])

    async def remote(*args):
        if side == "remote":
            raise asyncio.CancelledError()
        return {"total": 0, "data": []}

    monkeypatch.setattr(subject_service, "search_subject_by_name", local)
    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    with pytest.raises(asyncio.CancelledError):
        await SubjectCapability().execute(
            "search_mixed_subjects", db=object(), user_id=7, keyword="test"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled_side", ["local", "remote"])
async def test_strict_mixed_cancellation_wins_over_other_branch_failure(
    monkeypatch, cancelled_side
):
    import asyncio

    async def local(*args):
        if cancelled_side == "local":
            raise asyncio.CancelledError()
        raise RuntimeError("synthetic local failure")

    async def remote(*args):
        if cancelled_side == "remote":
            raise asyncio.CancelledError()
        raise RuntimeError("synthetic remote failure")

    monkeypatch.setattr(subject_service, "search_subject_by_name", local)
    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    with pytest.raises(asyncio.CancelledError):
        await SubjectCapability().execute(
            "search_mixed_subjects", db=object(), user_id=7, keyword="test"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", None),
        ("id", {}),
        ("id", True),
        ("id", -1),
        ("id", "501"),
        ("type", "synthetic-private-diagnostic"),
        ("type", True),
        ("type", 99),
        ("name", ""),
        ("name", None),
    ],
)
async def test_strict_remote_rejects_corrupt_identity_and_type_before_adapter(
    monkeypatch, caplog, field, value
):
    from app.schemas import adaptersV2

    async def remote(*args):
        return {
            "total": 1,
            "data": [{"id": 501, "type": 2, "name": "Synthetic", field: value}],
        }

    monkeypatch.setattr(subject_service, "search_bangumi_subjects", remote)
    logger = adaptersV2.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger=logger.name):
            result = await SubjectCapability().execute(
                "search_remote_subjects", keyword="test"
            )
    finally:
        logger.removeHandler(caplog.handler)
    assert result["success"] is False and result["error_type"] == "upstream_error"
    assert "synthetic-private" not in json.dumps(result)
    assert all(
        "synthetic-private" not in repr(entry.__dict__) for entry in caplog.records
    )
