"""Exercise authenticated schedule HTTP paths without replacing domain services."""

from datetime import time

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Schedule, User


@pytest.fixture
async def schedule_users(db_session):
    db_session.add_all(
        [
            User(id=7, username="schedule-owner", hashed_password="synthetic"),
            User(id=8, username="schedule-other", hashed_password="synthetic"),
        ]
    )
    await db_session.commit()


def headers(user_id=7, key="schedule-test"):
    return {
        "Authorization": "Bearer " + create_access_token({"sub": str(user_id)}),
        "Idempotency-Key": key,
    }


def payload(**updates):
    return {
        "source": "bangumi",
        "source_id": "100",
        "day_of_week": 2,
        "start_time": "20:30:00",
        "user_id": 8,
        **updates,
    }


async def seed_schedule(db_session):
    row = Schedule(
        user_id=8,
        source="bangumi",
        source_id="100",
        day_of_week=2,
        start_time=time(20, 30),
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def test_schedule_empty_list(api_client, schedule_users):
    response = await api_client.get("/api/v1/schedules/", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0}


async def test_schedule_create_serializes_and_injects_principal(
    api_client, schedule_users, db_session
):
    response = await api_client.post(
        "/api/v1/schedules/", headers=headers(), json=payload()
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["user_id"] == 7
    assert data["source_id"] == "100"
    assert data["start_time"] == "20:30:00"
    assert data["watch_time"] is None
    stored = await db_session.get(Schedule, data["id"])
    assert stored.user_id == 7
    assert stored.start_time == time(20, 30)


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("exists", [True, False], ids=["cross-user", "missing"])
async def test_schedule_denied_write_maps_to_404_and_preserves_owner(
    api_client, schedule_users, db_session, method, exists
):
    row = await seed_schedule(db_session)
    path = f"/api/v1/schedules/{row.id if exists else 9999}"
    kwargs = {"json": {"watch_day": 3}} if method == "put" else {}
    response = await api_client.request(method, path, headers=headers(), **kwargs)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Schedule operation was not completed"}
    await db_session.refresh(row)
    assert row.user_id == 8
    assert row.watch_day is None
    assert row.start_time == time(20, 30)


async def test_schedule_list_does_not_expose_other_users(
    api_client, schedule_users, db_session
):
    await seed_schedule(db_session)
    response = await api_client.get("/api/v1/schedules/", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "total": 0}
    owner_response = await api_client.get("/api/v1/schedules/", headers=headers(8))
    assert owner_response.status_code == 200, owner_response.text
    assert owner_response.json()["total"] == 1
    assert owner_response.json()["items"][0]["schedule"]["user_id"] == 8


@pytest.mark.parametrize(
    "updates,field",
    [
        ({"day_of_week": -1}, "day_of_week"),
        ({"day_of_week": 7}, "day_of_week"),
        ({"watch_day": 7}, "watch_day"),
        ({"start_time": "25:00:00"}, "start_time"),
        ({"source_id": ""}, "source_id"),
        ({"watch_type": 99}, "watch_type"),
    ],
)
async def test_schedule_invalid_input_is_422_without_writes(
    api_client, schedule_users, db_session, updates, field
):
    response = await api_client.post(
        "/api/v1/schedules/", headers=headers(), json=payload(**updates)
    )
    assert response.status_code == 422, response.text
    assert any(error["loc"] == ["body", field] for error in response.json()["detail"])
    assert (await db_session.execute(select(Schedule))).scalars().all() == []


@pytest.mark.parametrize("key", [None, " "])
async def test_schedule_missing_or_blank_key_is_422_without_writes(
    api_client, schedule_users, db_session, key
):
    request_headers = headers()
    if key is None:
        request_headers.pop("Idempotency-Key")
    else:
        request_headers["Idempotency-Key"] = key
    response = await api_client.post(
        "/api/v1/schedules/", headers=request_headers, json=payload()
    )
    assert response.status_code == 422, response.text
    assert (await db_session.execute(select(Schedule))).scalars().all() == []


@pytest.mark.parametrize("token_kind", ["invalid", "missing-user", "invalid-sub"])
async def test_schedule_auth_failure_uses_real_dependency(
    api_client, schedule_users, db_session, token_kind
):
    token = "invalid-test-token"
    if token_kind != "invalid":
        token = create_access_token(
            {"sub": "9999" if token_kind == "missing-user" else "abc"}
        )
    response = await api_client.post(
        "/api/v1/schedules/",
        json=payload(),
        headers={"Authorization": "Bearer " + token, "Idempotency-Key": "auth-test"},
    )
    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"
    assert (await db_session.execute(select(Schedule))).scalars().all() == []


async def test_schedule_service_exception_maps_to_http_500(
    api_client, schedule_users, monkeypatch
):
    from app.services.schedule_service import ScheduleService

    async def fail(_db, _user_id):
        raise RuntimeError("synthetic database failure")

    # Only fault injection replaces the service. Other tests execute it fully.
    monkeypatch.setattr(ScheduleService, "get_unified_user_schedules", fail)
    response = await api_client.get("/api/v1/schedules/", headers=headers())
    assert response.status_code == 500, response.text
    assert response.json() == {"detail": "获取排班记录失败"}
    assert "synthetic database failure" not in response.text


async def test_schedule_owner_update_and_delete_persist(
    api_client, schedule_users, db_session
):
    row = await seed_schedule(db_session)
    response = await api_client.put(
        f"/api/v1/schedules/{row.id}",
        headers=headers(8, "owner-update"),
        json={"watch_day": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json()["watch_day"] == 3
    assert response.json()["start_time"] == "20:30:00"
    await db_session.refresh(row)
    assert row.watch_day == 3
    row_id = row.id
    response = await api_client.delete(
        f"/api/v1/schedules/{row_id}", headers=headers(8, "owner-delete")
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    db_session.expire_all()
    assert await db_session.get(Schedule, row_id) is None


async def test_schedule_owner_time_update_serializes_for_dispatcher(
    api_client, schedule_users, db_session
):
    row = await seed_schedule(db_session)
    response = await api_client.put(
        f"/api/v1/schedules/{row.id}",
        headers=headers(8),
        json={"start_time": "21:30:00", "watch_time": "22:00:00"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["start_time"] == "21:30:00"
    assert response.json()["watch_time"] == "22:00:00"
    await db_session.refresh(row)
    assert row.start_time == time(21, 30)
    assert row.watch_time == time(22)


async def test_schedule_anonymous_write_is_denied_without_writes(
    api_client, db_session
):
    response = await api_client.post(
        "/api/v1/schedules/", json=payload(), headers={"Idempotency-Key": "anonymous"}
    )
    assert response.status_code == 401, response.text
    assert (await db_session.execute(select(Schedule))).scalars().all() == []
