"""Contract fixtures for collections, schedules, subjects, and statistics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.capabilities import collections as collections_capability
from app.capabilities import schedule as schedule_capability
from app.capabilities import stats as stats_capability
from app.capabilities import subjects as subjects_capability

from .model import Case, Environment


VERSION = "v1"

_COLLECTION = {
    "source": "bangumi",
    "source_id": "subject-101",
    "type": 3,
    "rate": 9,
    "comment": "A synthetic collection entry",
    "private": False,
    "tags": ["fantasy"],
    "ep_status": 4,
    "subject_type": 2,
    "user_id": 701,
}
_SCHEDULE = {
    "id": 31,
    "source": "bangumi",
    "source_id": "subject-101",
    "day_of_week": 2,
    "start_time": "20:00:00",
    "watch_day": 3,
    "watch_time": "21:00:00",
    "duration": 7,
    "user_id": 701,
}
_SUBJECT = {
    "id": 101,
    "name": "Synthetic Anime",
    "name_cn": "合成动画",
    "type": 2,
    "source": "bangumi",
    "source_id": "subject-101",
    "air_time": "2026-10-20T12:00:00",
    "air_weekday": 2,
}


def _record(environment: Environment, operation: str) -> None:
    environment.calls.append(operation)


def _assert_db_user(environment: Environment, db: Any, user_id: Any) -> None:
    assert db is environment.db
    assert user_id == environment.user.id


def _bind_trusted_user(value: Any, user_id: int) -> Any:
    if isinstance(value, dict):
        return {
            key: user_id if key == "user_id" else _bind_trusted_user(child, user_id)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_bind_trusted_user(child, user_id) for child in value]
    return deepcopy(value)


def _case(
    arguments: dict[str, Any],
    expected: dict[str, Any],
    prepare: Callable[[Environment], Any],
) -> Case:
    return Case(arguments=arguments, expected=expected, prepare=prepare)


def _collection_search_prepare(
    operation: str,
    result: dict[str, Any],
    *,
    dependency: str,
) -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, search: Any) -> dict[str, Any]:
            _assert_db_user(environment, db, search.user_id)
            _record(environment, operation)
            return _bind_trusted_user(result, environment.user.id)

        environment.monkeypatch.setattr(collections_capability, dependency, fake)

    return prepare


def _collection_lookup_prepare(
    operation: str,
    result: Any,
    *,
    dependency: str,
) -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, search: Any) -> Any:
            _assert_db_user(environment, db, search.user_id)
            assert search.source == "bangumi"
            _record(environment, operation)
            return _bind_trusted_user(result, environment.user.id)

        environment.monkeypatch.setattr(collections_capability, dependency, fake)

    return prepare


def _collection_create_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, data: Any) -> dict[str, Any]:
            _assert_db_user(environment, db, data.user_id)
            assert data.source == "bangumi"
            _record(environment, "collections.create")
            return {
                "id": 201,
                "source": data.source,
                "source_id": data.source_id,
                "type": int(data.type),
                "rate": data.rate,
                "user_id": data.user_id,
            }

        environment.monkeypatch.setattr(
            collections_capability, "create_collection", fake
        )

    return prepare


def _collection_update_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, data: Any) -> dict[str, Any]:
            _assert_db_user(environment, db, data.user_id)
            assert data.source == "bangumi"
            _record(environment, "collections.update")
            return {
                "id": 201,
                "source": data.source,
                "source_id": data.source_id,
                "type": int(data.type) if data.type is not None else None,
                "rate": data.rate,
                "user_id": data.user_id,
            }

        environment.monkeypatch.setattr(
            collections_capability, "update_collection", fake
        )

    return prepare


def _collection_upsert_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(
            db: Any, user_id: int, *, data: dict[str, Any]
        ) -> dict[str, Any]:
            _assert_db_user(environment, db, user_id)
            assert data["collection"]["source"] == "bangumi"
            _record(environment, "collections.upsert")
            return {
                "id": 202,
                **data["collection"],
                "user_id": user_id,
            }

        environment.monkeypatch.setattr(
            collections_capability, "upsert_collection", fake
        )

    return prepare


def _collection_batch_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, batch: Any, user_id: int) -> int:
            _assert_db_user(environment, db, user_id)
            assert len(batch.collections) == 2
            assert all(
                item.user_id == environment.user.id for item in batch.collections
            )
            _record(environment, "collections.batch_upsert")
            return len(batch.collections)

        environment.monkeypatch.setattr(
            collections_capability, "batch_upsert_collections", fake
        )

    return prepare


def _collection_import_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, data: dict[str, Any], user_id: int) -> int:
            _assert_db_user(environment, db, user_id)
            assert data["data"]
            assert data["data"][0]["subject"]["name"] == "Synthetic Anime"
            _record(environment, "collections.import_json")
            return 2

        environment.monkeypatch.setattr(
            collections_capability, "import_json_collections", fake
        )

    return prepare


def _collection_bangumi_sync_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(*, db: Any, user: Any, request_data: Any) -> int:
            assert db is environment.db
            assert user is environment.user
            assert user.id == environment.user.id
            assert request_data.subject_type == 2
            _record(environment, "collections.sync_bangumi")
            return 2

        environment.monkeypatch.setattr(
            collections_capability, "sync_user_collections", fake
        )

    return prepare


def _collection_douban_sync_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(user_id: int, db: Any, data: list[dict[str, Any]]) -> int:
            _assert_db_user(environment, db, user_id)
            assert len(data) == 2
            assert data[0]["interest"]["subject"]["type"] == "tv"
            _record(environment, "collections.sync_douban")
            return len(data)

        environment.monkeypatch.setattr(
            collections_capability, "sync_user_collections_douban", fake
        )

    return prepare


def _prepare_schedule_dependency(
    method: str,
    operation: str,
    result: Any,
    *,
    user_argument: int,
) -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, *args: Any) -> Any:
            assert db is environment.db
            _assert_db_user(environment, db, args[user_argument])
            if method in {"create_schedule", "upsert_schedule"}:
                assert args[1].user_id == environment.user.id
                assert args[1].source == "bangumi"
            elif method == "bulk_upsert_schedules":
                assert len(args[1].items) == 2
                assert all(
                    item.user_id == environment.user.id for item in args[1].items
                )
            _record(environment, operation)
            return _bind_trusted_user(result, environment.user.id)

        environment.monkeypatch.setattr(
            schedule_capability.ScheduleService, method, fake
        )

    return prepare


def _subject_search_prepare(
    operation: str,
    result: dict[str, Any],
    *,
    dependency: str,
    local: bool,
) -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, search: Any, **options: Any) -> dict[str, Any]:
            assert options == (
                {"strict": True}
                if dependency in {"search_subject_cloud", "search_mixed"}
                else {}
            )
            if local:
                _assert_db_user(environment, db, search.user_id)
            else:
                assert db is None
                assert search.user_id is None
                assert environment.user.id > 0
            _record(environment, operation)
            return deepcopy(result)

        environment.monkeypatch.setattr(subjects_capability, dependency, fake)

    return prepare


def _subject_lookup_prepare() -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(db: Any, search: Any) -> dict[str, Any]:
            _assert_db_user(environment, db, search.user_id)
            assert search.source == "bangumi"
            _record(environment, "subjects.get_subject_by_source")
            return {
                "subject": deepcopy(_SUBJECT),
                "collection": {"type": 3, "rate": 9},
            }

        environment.monkeypatch.setattr(
            subjects_capability, "get_subject_by_source", fake
        )

    return prepare


def _stats_prepare(
    dependency: str, result: dict[str, Any]
) -> Callable[[Environment], Any]:
    async def prepare(environment: Environment) -> None:
        async def fake(*args: Any) -> dict[str, Any]:
            if dependency == "get_collection_statistics":
                user_id, db, subject_type = args
                _assert_db_user(environment, db, user_id)
                assert subject_type == 2
            else:
                user_id, db = args
                _assert_db_user(environment, db, user_id)
            _record(environment, f"stats.{dependency}")
            return deepcopy(result)

        environment.monkeypatch.setattr(stats_capability, dependency, fake)

    return prepare


CASES: dict[tuple[str, str], Case] = {
    ("list_collections", VERSION): _case(
        {"type": 2, "status": 3, "skip": 0, "limit": 5, "sort_by": "updated_at"},
        {
            "total": 2,
            "collections": [
                {"source": "bangumi", "source_id": "subject-101", "type": 3}
            ],
        },
        _collection_search_prepare(
            "collections.list",
            {"total": 2, "items": [_COLLECTION]},
            dependency="get_user_collections",
        ),
    ),
    ("get_collection", VERSION): _case(
        {"source": "bangumi", "source_id": "subject-101"},
        {
            "collection": {
                "collection": {
                    "source": "bangumi",
                    "source_id": "subject-101",
                },
                "subject": {"name": "Synthetic Anime"},
            }
        },
        _collection_lookup_prepare(
            "collections.get",
            {
                "collection": _COLLECTION,
                "subject": _SUBJECT,
            },
            dependency="get_collection",
        ),
    ),
    ("search_collections", VERSION): _case(
        {"keyword": "Synthetic", "type": 2, "status": 3, "limit": 5},
        {
            "total": 1,
            "collections": [
                {"source": "bangumi", "source_id": "subject-101", "type": 3}
            ],
        },
        _collection_search_prepare(
            "collections.search",
            {"total": 1, "items": [_COLLECTION]},
            dependency="search_collections",
        ),
    ),
    ("create_collection", VERSION): _case(
        {
            "source": "bangumi",
            "source_id": "subject-101",
            "type": 3,
            "rate": 9,
            "comment": "A synthetic collection entry",
            "private": False,
            "tags": ["fantasy"],
            "ep_status": 4,
            "subject_type": 2,
        },
        {
            "collection": {
                "id": 201,
                "source": "bangumi",
                "source_id": "subject-101",
                "rate": 9,
            }
        },
        _collection_create_prepare(),
    ),
    ("update_collection", VERSION): _case(
        {
            "source": "bangumi",
            "source_id": "subject-101",
            "type": 2,
            "rate": 10,
            "comment": "Updated synthetic entry",
        },
        {
            "collection": {
                "id": 201,
                "source": "bangumi",
                "source_id": "subject-101",
                "rate": 10,
            }
        },
        _collection_update_prepare(),
    ),
    ("delete_collection", VERSION): _case(
        {"source": "bangumi", "source_id": "subject-101"},
        {"deleted": True},
        _collection_lookup_prepare(
            "collections.delete",
            True,
            dependency="delete_collection",
        ),
    ),
    ("upsert_collection", VERSION): _case(
        {
            "source": "bangumi",
            "source_id": "subject-101",
            "type": 3,
            "rate": 8,
            "tags": ["fantasy", "adventure"],
        },
        {
            "collection": {
                "id": 202,
                "source": "bangumi",
                "source_id": "subject-101",
                "rate": 8,
            }
        },
        _collection_upsert_prepare(),
    ),
    ("batch_upsert_collections", VERSION): _case(
        {
            "items": [
                {
                    "source": "bangumi",
                    "source_id": "subject-101",
                    "type": 3,
                    "subject_type": 2,
                },
                {
                    "source": "bangumi",
                    "source_id": "subject-102",
                    "type": 1,
                    "subject_type": 2,
                },
            ],
            "idempotency_key": "collections-batch-101",
        },
        {"processed_count": 2, "requested_count": 2},
        _collection_batch_prepare(),
    ),
    ("import_json_collections", VERSION): _case(
        {
            "data": {
                "data": [
                    {
                        "subject_id": "subject-101",
                        "type": 3,
                        "rate": 9,
                        "subject": {
                            "id": 101,
                            "name": "Synthetic Anime",
                            "type": 2,
                        },
                    },
                    {
                        "subject_id": "subject-102",
                        "type": 1,
                        "rate": 8,
                        "subject": {
                            "id": 102,
                            "name": "Synthetic Series",
                            "type": 2,
                        },
                    },
                ]
            },
            "idempotency_key": "collections-import-101",
        },
        {"processed_count": 2},
        _collection_import_prepare(),
    ),
    ("sync_bangumi_collections", VERSION): _case(
        {"subject_type": 2, "limit": 3, "offset": 0},
        {"processed_count": 2},
        _collection_bangumi_sync_prepare(),
    ),
    ("sync_douban_collections", VERSION): _case(
        {
            "data": [
                {
                    "interest": {
                        "status": "done",
                        "subject": {"id": "douban-501", "type": "tv"},
                        "rating": {"value": 4.5},
                    }
                },
                {
                    "interest": {
                        "status": "doing",
                        "subject": {"id": "douban-502", "type": "movie"},
                        "rating": {"value": 4.0},
                    }
                },
            ]
        },
        {"processed_count": 2},
        _collection_douban_sync_prepare(),
    ),
    ("list_schedules", VERSION): _case(
        {},
        {
            "count": 1,
            "schedules": [{"id": 31, "source": "bangumi", "source_id": "subject-101"}],
        },
        _prepare_schedule_dependency(
            "get_user_schedules", "schedule.list", [_SCHEDULE], user_argument=0
        ),
    ),
    ("create_schedule", VERSION): _case(
        {
            "source": "bangumi",
            "source_id": "subject-101",
            "day_of_week": 2,
            "start_time": "20:00:00",
            "watch_day": 3,
            "watch_time": "21:00:00",
            "duration": 7,
            "idempotency_key": "schedule-create-101",
        },
        {"schedule": {"id": 31, "source": "bangumi", "source_id": "subject-101"}},
        _prepare_schedule_dependency(
            "create_schedule", "schedule.create", _SCHEDULE, user_argument=0
        ),
    ),
    ("update_schedule", VERSION): _case(
        {
            "schedule_id": 31,
            "day_of_week": 4,
            "start_time": "19:30:00",
            "idempotency_key": "schedule-update-101",
        },
        {"schedule": {"id": 31, "day_of_week": 4}},
        _prepare_schedule_dependency(
            "update_schedule",
            "schedule.update",
            {**_SCHEDULE, "day_of_week": 4, "start_time": "19:30:00"},
            user_argument=1,
        ),
    ),
    ("delete_schedule", VERSION): _case(
        {"schedule_id": 31, "idempotency_key": "schedule-delete-101"},
        {"deleted": True},
        _prepare_schedule_dependency(
            "delete_schedule", "schedule.delete", True, user_argument=1
        ),
    ),
    ("list_schedules_by_day", VERSION): _case(
        {"day_of_week": 2},
        {"count": 1, "schedules": [{"id": 31, "day_of_week": 2}]},
        _prepare_schedule_dependency(
            "get_schedules_by_day", "schedule.list_by_day", [_SCHEDULE], user_argument=0
        ),
    ),
    ("list_unified_schedules", VERSION): _case(
        {},
        {
            "count": 1,
            "schedules": [
                {"schedule": {"id": 31}, "subject": {"name": "Synthetic Anime"}}
            ],
        },
        _prepare_schedule_dependency(
            "get_unified_user_schedules",
            "schedule.list_unified",
            {
                "items": [
                    {
                        "schedule": _SCHEDULE,
                        "subject": _SUBJECT,
                        "collection": {"type": 3, "rate": 9},
                    }
                ],
                "total": 1,
            },
            user_argument=0,
        ),
    ),
    ("upsert_schedule", VERSION): _case(
        {
            "source": "bangumi",
            "source_id": "subject-101",
            "day_of_week": 2,
            "start_time": "20:00:00",
            "watch_day": 3,
            "watch_time": "21:00:00",
            "duration": 7,
            "idempotency_key": "schedule-upsert-101",
        },
        {"schedule": {"id": 31, "source": "bangumi", "source_id": "subject-101"}},
        _prepare_schedule_dependency(
            "upsert_schedule", "schedule.upsert", _SCHEDULE, user_argument=0
        ),
    ),
    ("bulk_upsert_schedules", VERSION): _case(
        {
            "items": [
                {
                    "source": "bangumi",
                    "source_id": "subject-101",
                    "day_of_week": 2,
                    "start_time": "20:00:00",
                    "watch_day": 3,
                    "watch_time": "21:00:00",
                    "duration": 7,
                },
                {
                    "source": "bangumi",
                    "source_id": "subject-102",
                    "day_of_week": 5,
                    "start_time": "18:30:00",
                    "watch_day": 5,
                    "watch_time": "20:00:00",
                    "duration": 14,
                },
            ],
            "idempotency_key": "schedule-bulk-101",
        },
        {"count": 2, "schedules": [{"id": 31}, {"id": 32}]},
        _prepare_schedule_dependency(
            "bulk_upsert_schedules",
            "schedule.bulk_upsert",
            [_SCHEDULE, {**_SCHEDULE, "id": 32, "source_id": "subject-102"}],
            user_argument=0,
        ),
    ),
    ("sync_bangumi_schedule", VERSION): _case(
        {"idempotency_key": "schedule-sync-101"},
        {"count": 1, "schedules": [{"id": 31, "source_id": "subject-101"}]},
        _prepare_schedule_dependency(
            "sync_bangumi_calendar",
            "schedule.sync_bangumi",
            {"items": [_SCHEDULE], "total": 1},
            user_argument=0,
        ),
    ),
    ("get_subject", VERSION): _case(
        {"source": "bangumi", "source_id": "subject-101"},
        {"subject": {"subject": {"name": "Synthetic Anime"}}},
        _subject_lookup_prepare(),
    ),
    ("search_local_subjects", VERSION): _case(
        {"keyword": "Synthetic", "type": 2, "skip": 0, "limit": 5},
        {
            "total": 1,
            "subjects": [
                {"subject": {"id": 101, "name": "Synthetic Anime"}, "collection": None}
            ],
        },
        _subject_search_prepare(
            "subjects.search_local",
            {"total": 1, "items": [{"subject": _SUBJECT, "collection": None}]},
            dependency="search_subject_by_name",
            local=True,
        ),
    ),
    ("search_remote_subjects", VERSION): _case(
        {"keyword": "Synthetic", "type": 2, "skip": 0, "limit": 5},
        {
            "total": 1,
            "subjects": [
                {"subject": {"id": 101, "name": "Synthetic Anime"}, "collection": None}
            ],
        },
        _subject_search_prepare(
            "subjects.search_remote",
            {"total": 1, "items": [{"subject": _SUBJECT, "collection": None}]},
            dependency="search_subject_cloud",
            local=False,
        ),
    ),
    ("search_mixed_subjects", VERSION): _case(
        {"keyword": "Synthetic", "type": 2, "skip": 0, "limit": 5},
        {
            "total": 1,
            "subjects": [
                {"subject": {"id": 101, "name": "Synthetic Anime"}, "collection": None}
            ],
        },
        _subject_search_prepare(
            "subjects.search_mixed",
            {"total": 1, "items": [{"subject": _SUBJECT, "collection": None}]},
            dependency="search_mixed",
            local=True,
        ),
    ),
    ("get_subject_air_time", VERSION): _case(
        {"source": "bangumi", "source_id": "subject-101"},
        {"source": "bangumi", "source_id": "subject-101", "air_weekday": 2},
        _subject_lookup_prepare(),
    ),
    ("get_user_stats", VERSION): _case(
        {},
        {"stats": {"anime": 2, "books": 1, "total": 3}},
        _stats_prepare(
            "get_user_stats",
            {"anime": 2, "books": 1, "music": 0, "games": 0, "real": 0, "total": 3},
        ),
    ),
    ("get_collection_statistics", VERSION): _case(
        {"subject_type": 2},
        {
            "statistics": {
                "subject_type": 2,
                "total": 2,
                "status_counts": {
                    "wish": 1,
                    "watched": 1,
                    "watching": 0,
                    "on_hold": 0,
                    "dropped": 0,
                },
                "top_genres": [{"name": "fantasy", "count": 2}],
                "complete": True,
                "genre_subject_count": 2,
                "genre_complete": True,
            }
        },
        _stats_prepare(
            "get_collection_statistics",
            {
                "subject_type": 2,
                "total": 2,
                "status_counts": {
                    "wish": 1,
                    "watched": 1,
                    "watching": 0,
                    "on_hold": 0,
                    "dropped": 0,
                },
                "top_genres": [{"name": "fantasy", "count": 2}],
                "complete": True,
                "genre_subject_count": 2,
                "genre_complete": True,
            },
        ),
    ),
}
