"""Real schedule read queries, ownership, serialization and safe diagnostics."""

from datetime import time
import json
import logging

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.capabilities.schedule import ScheduleCapability
from app.harness.normalizer import ResultNormalizer, SchemaContractError, validate_input
from app.models import (
    Collection,
    CollectionStatus,
    Schedule,
    Subject,
    SubjectType,
    User,
)
from app.models.enums import WatchType
from app.repositories import schedule_repo
from app.services import schedule_service
from app.services.schedule_service import ScheduleService

READS = {
    "list_schedules": ("get_user_schedules", "get_by_user", {}),
    "list_schedules_by_day": ("get_schedules_by_day", "get_by_day", {"day_of_week": 0}),
    "list_unified_schedules": (
        "get_unified_user_schedules",
        "get_unified_schedules_by_user",
        {},
    ),
}


async def snapshot(db):
    await db.flush()
    return {
        model.__name__: sorted(
            (
                item.model_dump_json()
                for item in (
                    await db.execute(
                        select(model).execution_options(populate_existing=True)
                    )
                ).scalars()
            ),
        )
        for model in (Schedule, Subject, Collection)
    }


async def verify_queries(db):
    users = [User(username=f"schedule-read-{i}") for i in range(3)]
    db.add_all(users)
    await db.commit()
    a, b, empty = [u.id for u in users]
    db.add(Subject(source_id="shared", name="Shared", type=SubjectType.ANIME))
    db.add(
        Subject(source_id="no-collection", name="No collection", type=SubjectType.ANIME)
    )
    for owner, comment in ((a, "owner-a-private"), (b, "owner-b-private")):
        db.add(
            Collection(
                user_id=owner,
                source_id="shared",
                type=CollectionStatus.DO,
                private=True,
                comment=comment,
                rate=8 if owner == a else 2,
            )
        )
    db.add(
        Collection(
            user_id=b,
            source_id="foreign-collection",
            type=CollectionStatus.DO,
            private=True,
            comment="foreign-only-private",
        )
    )
    db.add(
        Collection(
            user_id=a,
            source_id="missing-subject",
            type=CollectionStatus.DO,
            private=True,
            comment="owned-without-subject",
        )
    )
    for owner, source_id, day, hour, watch in (
        (a, "shared", 6, 22, 0),
        (b, "shared", 0, 9, 6),
        (a, "no-collection", 0, 20, 6),
        (a, "missing-subject", 0, 8, 6),
        (a, "foreign-collection", 2, 18, 0),
    ):
        db.add(
            Schedule(
                user_id=owner,
                source="bangumi",
                source_id=source_id,
                day_of_week=day,
                start_time=time(hour, 15, 30),
                watch_day=watch,
                watch_time=time(23, 0),
                watch_type=WatchType.NEW,
                duration=None,
            )
        )
    await db.commit()
    before = await snapshot(db)
    cap = ScheduleCapability()
    all_rows = await cap.execute("list_schedules", db=db, user_id=a)
    assert all_rows["success"] and all_rows["count"] == 4
    assert [r["source_id"] for r in all_rows["schedules"]] == [
        "missing-subject",
        "no-collection",
        "foreign-collection",
        "shared",
    ]
    assert all_rows["schedules"][0]["start_time"] == "08:15:30"
    assert all_rows["schedules"][0]["watch_type"] == 4
    assert all_rows["schedules"][0]["duration"] is None
    for day, count in ((0, 2), (6, 1), (1, 0)):
        rows = await cap.execute(
            "list_schedules_by_day", db=db, user_id=a, day_of_week=day
        )
        assert rows["count"] == len(rows["schedules"]) == count
        assert all(row["day_of_week"] == day for row in rows["schedules"])
    for owner, private in ((a, "owner-a-private"), (b, "owner-b-private")):
        result = await cap.execute("list_unified_schedules", db=db, user_id=owner)
        assert result["success"] and result["count"] == len(result["schedules"])
        items = {r["schedule"]["source_id"]: r for r in result["schedules"]}
        assert items["shared"]["collection"]["comment"] == private
        assert items["shared"]["subject"]["name"] == "Shared"
        if owner == a:
            assert items["no-collection"]["collection"] is None
            assert items["missing-subject"]["subject"] is None
            assert (
                items["missing-subject"]["collection"]["comment"]
                == "owned-without-subject"
            )
            assert items["foreign-collection"]["collection"] is None
            assert "owner-b-private" not in json.dumps(result)
            assert "foreign-only-private" not in json.dumps(result)
        assert "user_id" not in json.dumps(result)
        descriptor = next(
            d for d in cap.actions() if d.name == "list_unified_schedules"
        )
        normalized = ResultNormalizer().normalize(
            result,
            descriptor=descriptor,
            run_id="sql",
            decision_id="sql",
            invocation_id="sql",
            trace_id="sql",
        )
        assert normalized.status == "succeeded"
        assert normalized.safe_output == {
            k: v for k, v in result.items() if k != "success"
        }
        assert not normalized.artifacts
    assert "user_id" not in json.dumps(all_rows)
    descriptor = next(d for d in cap.actions() if d.name == "list_schedules")
    large = {"success": True, "schedules": all_rows["schedules"] * 1000, "count": 4000}
    bounded = ResultNormalizer().normalize(
        large,
        descriptor=descriptor,
        run_id="large",
        decision_id="large",
        invocation_id="large",
        trace_id="large",
    )
    assert bounded.artifacts and bounded.artifacts[0]["kind"] == "bounded_output"
    assert bounded.provenance["bounded"] is True
    if bounded.status == "succeeded":
        assert len(bounded.safe_output["schedules"]) < large["count"]
    else:
        assert bounded.error_code == "payload_too_large"
    for action, (_, _, args) in READS.items():
        result = await cap.execute(action, db=db, user_id=empty, **args)
        assert result == {"success": True, "schedules": [], "count": 0}
    assert await snapshot(db) == before


@pytest.mark.asyncio
async def test_read_queries_sqlite(db_session):
    await verify_queries(db_session)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_read_queries_postgres(postgres_session):
    await verify_queries(postgres_session)


@pytest.mark.parametrize("action", READS)
@pytest.mark.parametrize(
    "extra", [{"save": True}, {"idempotency_key": "x"}, {"filter": {}}]
)
def test_inputs_reject_write_and_unregistered_filters(action, extra):
    descriptor = next(d for d in ScheduleCapability().actions() if d.name == action)
    with pytest.raises(SchemaContractError):
        validate_input({**READS[action][2], **extra}, descriptor)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS)
async def test_read_value_error_is_safe_invalid_args(action, monkeypatch):
    async def fail(*args):
        raise ValueError("synthetic-private-value")

    monkeypatch.setattr(ScheduleService, READS[action][0], fail)
    result = await ScheduleCapability().execute(
        action, db=object(), user_id=7, **READS[action][2]
    )
    assert result["error_type"] == "invalid_args"
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS)
async def test_read_service_and_repository_logs_hide_sql_diagnostics(
    action, monkeypatch, caplog
):
    class BrokenSession:
        async def execute(self, *args, **kwargs):
            raise SQLAlchemyError("synthetic-private-sql-parameter")

    method, _, args = READS[action]
    loggers = (schedule_repo.logger, schedule_service.logger)
    for logger in loggers:
        logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(SQLAlchemyError):
                await getattr(ScheduleService, method)(
                    BrokenSession(), 7, *args.values()
                )
    finally:
        for logger in loggers:
            logger.removeHandler(caplog.handler)
    assert "synthetic-private-sql-parameter" not in caplog.text
    assert len(caplog.records) >= 2
    assert all(
        "synthetic-private" not in repr(r.__dict__) and r.exc_info is None
        for r in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS)
@pytest.mark.parametrize("user_id", [True, 0, -1, "7"])
async def test_invalid_direct_principal_never_queries(action, user_id, monkeypatch):
    async def forbidden(*args):
        pytest.fail("Invalid principal reached Service")

    monkeypatch.setattr(ScheduleService, READS[action][0], forbidden)
    result = await ScheduleCapability().execute(
        action, db=object(), user_id=user_id, **READS[action][2]
    )
    assert result["success"] is False and result["error_type"] == "unauthorized"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"items": []}, {"total": 0}])
async def test_unified_missing_service_fields_are_not_fabricated_as_empty(
    payload, monkeypatch
):
    async def malformed(*args):
        return payload

    monkeypatch.setattr(ScheduleService, "get_unified_user_schedules", malformed)
    result = await ScheduleCapability().execute(
        "list_unified_schedules", db=object(), user_id=7
    )
    assert result["success"] is False
