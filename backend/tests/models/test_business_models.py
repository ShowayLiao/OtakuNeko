"""Persisted business constraints and public serialization contracts."""

import json
from datetime import datetime, time, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Collection, Schedule, Subject, User
from app.models.enums import CollectionStatus, SubjectType, WatchType
from app.schemas.collection import CollectionCreate, CollectionRead
from app.schemas.schedule import ScheduleCreate, ScheduleRead
from app.schemas.subject import SubjectRead
from app.schemas.user import UserRead


@pytest.mark.parametrize(
    "field,value",
    [
        ("rate", -1),
        ("rate", 11),
        ("type", 99),
        ("source", "unknown"),
        ("source_id", ""),
        ("comment", "x" * 501),
    ],
)
def test_collection_input_rejects_invalid_fields(field, value):
    data = {"user_id": 7, "source": "bangumi", "source_id": "100", "type": 2}
    data[field] = value
    with pytest.raises(ValidationError) as caught:
        CollectionCreate.model_validate(data)
    assert any(error["loc"] == (field,) for error in caught.value.errors())


@pytest.mark.parametrize("rate", [0, 10])
def test_collection_rating_boundaries_are_valid(rate):
    data = CollectionCreate.model_validate(
        {"user_id": 7, "source_id": "100", "type": 2, "rate": rate}
    )
    assert data.rate == rate
    assert data.type is CollectionStatus.COLLECT


@pytest.mark.parametrize(
    "field,value",
    [
        ("day_of_week", -1),
        ("day_of_week", 7),
        ("watch_day", -1),
        ("watch_day", 7),
        ("start_time", "invalid"),
        ("watch_type", 99),
        ("source_id", ""),
        ("source_id", "x" * 21),
    ],
)
def test_schedule_input_rejects_invalid_fields(field, value):
    data = {
        "user_id": 7,
        "source": "bangumi",
        "source_id": "100",
        "day_of_week": 0,
        "start_time": "20:30:00",
    }
    data[field] = value
    with pytest.raises(ValidationError) as caught:
        ScheduleCreate.model_validate(data)
    assert any(error["loc"] == (field,) for error in caught.value.errors())


@pytest.mark.parametrize("day", [0, 6])
def test_schedule_weekday_boundaries_are_valid(day):
    data = ScheduleCreate.model_validate(
        {
            "user_id": 7,
            "source": "bangumi",
            "source_id": "100",
            "day_of_week": day,
            "start_time": "20:30:00",
        }
    )
    assert data.day_of_week == day
    assert data.start_time == time(20, 30)


def test_public_user_serialization_excludes_password():
    user = User(
        id=7,
        username="synthetic",
        hashed_password="synthetic-private",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    public = UserRead.model_validate(user)
    data = json.loads(public.model_dump_json())
    assert data["id"] == 7
    assert data["username"] == "synthetic"
    assert "hashed_password" not in data
    assert "synthetic-private" not in public.model_dump_json()
    assert UserRead.model_validate_json(public.model_dump_json()) == public


@pytest.mark.parametrize("kind", ["collection", "schedule", "subject"])
async def test_business_models_persist_and_serialize_json(db_session, kind):
    row: Collection | Schedule | Subject
    schema: type[CollectionRead] | type[ScheduleRead] | type[SubjectRead]
    if kind == "collection":
        row = Collection(
            user_id=7,
            source_id="100",
            type=CollectionStatus.DO,
            tags=["动画", "tag"],
            comment="测试",
            rate=8,
        )
        schema = CollectionRead
    elif kind == "schedule":
        row = Schedule(
            user_id=7,
            source="bangumi",
            source_id="100",
            day_of_week=2,
            start_time=time(20, 30),
            watch_type=WatchType.NEW,
        )
        schema = ScheduleRead
    else:
        row = Subject(
            source="bangumi",
            source_id="100",
            type=SubjectType.ANIME,
            name="测试番剧",
            images={"large": "synthetic-image"},
            tags=[{"name": "动画", "count": 2}],
        )
        schema = SubjectRead
    db_session.add(User(id=7, username="model-user", hashed_password="synthetic"))
    db_session.add(row)
    await db_session.commit()
    row_id = row.id
    db_session.expire_all()
    loaded = await db_session.get(type(row), row_id)
    public = schema.model_validate(loaded, from_attributes=True)
    dumped = public.model_dump_json()
    data = json.loads(dumped)
    assert loaded.id == row_id
    if kind != "collection":
        assert data["id"] == row_id
    assert data["source_id"] == "100"
    assert schema.model_validate_json(dumped) == public
    if kind == "collection":
        assert data["type"] == 3
        assert data["tags"] == ["动画", "tag"]
        assert data["comment"] == "测试"
        assert data["updated_at"]
    elif kind == "schedule":
        assert data["start_time"] == "20:30:00"
        assert data["watch_type"] == 4
        assert data["watch_time"] is None
    else:
        assert data["type"] == 2
        assert data["images"] == {"large": "synthetic-image"}
        assert data["tags"] == [{"name": "动画", "count": 2}]


@pytest.mark.parametrize("kind", ["collection", "schedule", "subject"])
async def test_database_unique_business_key_and_rollback(db_session, kind):
    def make_row(source="bangumi", user_id=7):
        if kind == "collection":
            return Collection(user_id=user_id, source=source, source_id="100", type=2)
        if kind == "schedule":
            return Schedule(
                user_id=user_id,
                source=source,
                source_id="100",
                day_of_week=2,
                start_time=time(20, 30),
            )
        return Subject(source=source, source_id="100", type=2, name="synthetic")

    db_session.add_all(
        [
            User(id=7, username="model-owner", hashed_password="synthetic"),
            User(id=8, username="model-other", hashed_password="synthetic"),
        ]
    )
    row = make_row()
    db_session.add(row)
    await db_session.commit()
    row_type = type(row)
    db_session.add(make_row())
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    rows = (await db_session.execute(select(row_type))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_id == "100"
    # Same external ID on another source is legal; user-owned keys also allow
    # a different owner. The session remains usable after rollback.
    db_session.add(make_row(source="douban"))
    if kind != "subject":
        db_session.add(make_row(user_id=8))
    await db_session.commit()
    rows = (await db_session.execute(select(row_type))).scalars().all()
    assert len(rows) == (2 if kind == "subject" else 3)


def test_json_defaults_are_not_shared_between_model_instances():
    first = Subject(source_id="100", type=2, name="first")
    second = Subject(source_id="101", type=2, name="second")
    first.tags.append({"name": "synthetic"})
    first.images["large"] = "synthetic-image"
    assert second.tags == []
    assert second.images == {}
    first_collection = Collection(user_id=7, source_id="100", type=2)
    second_collection = Collection(user_id=7, source_id="101", type=2)
    first_collection.tags.append("synthetic")
    assert second_collection.tags == []
