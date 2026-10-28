"""Load and seed isolated synthetic fixtures for anime evaluations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Collection, CollectionStatus, Subject, SubjectType


_FIXTURE_FILES = {
    "user": "user.synthetic.json",
    "catalog": "catalog.synthetic.json",
    "calendar": "calendar.synthetic.json",
    "search_snapshots": "search-snapshots.synthetic.json",
}
_COLLECTION_STATUSES = {
    "planned": CollectionStatus.WISH,
    "complete": CollectionStatus.COLLECT,
    "watching": CollectionStatus.DO,
    "on_hold": CollectionStatus.ON_HOLD,
    "dropped": CollectionStatus.DROPPED,
}


@dataclass(frozen=True)
class AnimeFixtureSet:
    """A validated, deeply immutable collection of synthetic fixtures."""

    fixture_dir: Path
    user: Mapping[str, Any]
    catalog: Mapping[str, Any]
    calendar: Mapping[str, Any]
    search_snapshots: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field_name in ("user", "catalog", "calendar", "search_snapshots"):
            object.__setattr__(
                self,
                field_name,
                _freeze_fixture_value(getattr(self, field_name)),
            )


def load_anime_fixture_set(fixture_dir: str | Path) -> AnimeFixtureSet:
    """Read and validate the four v1 synthetic fixture files from one directory."""
    directory = Path(fixture_dir).resolve()
    payloads: dict[str, dict[str, Any]] = {}
    for label, filename in _FIXTURE_FILES.items():
        try:
            text = (directory / filename).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise ValueError(f"unable to read {label} anime fixture") from None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise ValueError(f"invalid JSON in {label} anime fixture") from None
        if not isinstance(payload, dict):
            raise ValueError(f"{label} anime fixture must be an object")
        payloads[label] = payload

    for label, payload in payloads.items():
        schema_version = payload.get("schema_version")
        if type(schema_version) is not int or schema_version != 1:
            raise ValueError(f"unsupported {label} anime fixture schema_version")

    catalog = payloads["catalog"]
    if catalog.get("synthetic") is not True:
        raise ValueError("catalog anime fixture must be marked synthetic")

    anime_by_id = _validate_catalog(catalog)
    _validate_user_fixture(payloads["user"], anime_by_id)
    _validate_calendar_fixture(payloads["calendar"])
    _validate_search_snapshots(payloads["search_snapshots"], anime_by_id)

    return AnimeFixtureSet(
        fixture_dir=directory,
        user=payloads["user"],
        catalog=catalog,
        calendar=payloads["calendar"],
        search_snapshots=payloads["search_snapshots"],
    )


async def seed_anime_fixture(
    session: AsyncSession,
    *,
    test_user_id: int,
    fixture_set: AnimeFixtureSet,
) -> None:
    """Add synthetic catalog and collection rows for a trusted test user."""
    if type(test_user_id) is not int:
        raise ValueError("test_user_id must be an integer")

    subjects = [
        Subject(
            source="bangumi",
            source_id=anime["id"],
            type=SubjectType.ANIME,
            name=anime["title"],
            tags=[{"name": tag} for tag in anime.get("tags", [])],
            meta_tags=anime.get("tags", []),
            eps=anime.get("episodes"),
        )
        for anime in fixture_set.catalog["anime"]
    ]
    collections = [
        Collection(
            user_id=test_user_id,
            source="bangumi",
            source_id=entry["anime_id"],
            type=_COLLECTION_STATUSES[entry["status"]],
            rate=entry["rating"],
            ep_status=entry["episodes_watched"],
            subject_type=int(SubjectType.ANIME),
        )
        for entry in fixture_set.user["collection"]
    ]
    session.add_all([*subjects, *collections])
    await session.flush()


async def collection_snapshot(
    session: AsyncSession,
    *,
    user_id: int,
) -> dict[str, dict[str, object]]:
    """Return persisted Bangumi anime collections for one user, keyed by source ID."""
    result = await session.scalars(
        select(Collection)
        .where(
            Collection.user_id == user_id,
            Collection.source == "bangumi",
            Collection.subject_type == int(SubjectType.ANIME),
        )
        .order_by(Collection.source_id)
    )
    return {
        collection.source_id: {
            "type": int(collection.type),
            "rate": collection.rate,
            "episodes_watched": collection.ep_status,
        }
        for collection in result.all()
    }


def _validate_catalog(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    anime = catalog.get("anime")
    if not isinstance(anime, list):
        raise ValueError("catalog anime fixture must contain an anime list")

    anime_by_id: dict[str, dict[str, Any]] = {}
    for entry in anime:
        if not isinstance(entry, dict):
            raise ValueError("catalog anime entries must be objects")
        anime_id = entry.get("id")
        title = entry.get("title")
        if not isinstance(anime_id, str) or not anime_id.strip():
            raise ValueError("catalog anime entries require a non-empty id")
        if anime_id in anime_by_id:
            raise ValueError("catalog contains duplicate anime IDs")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("catalog anime entries require a title")
        episodes = entry.get("episodes")
        if episodes is not None and not _is_non_negative_int(episodes):
            raise ValueError(
                "catalog anime episode counts must be non-negative integers"
            )
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("catalog anime tags must be a list of strings")
        anime_by_id[anime_id] = entry

    return anime_by_id


def _validate_user_fixture(
    user: dict[str, Any],
    anime_by_id: dict[str, dict[str, Any]],
) -> None:
    collection = user.get("collection")
    if not isinstance(collection, list):
        raise ValueError("user anime fixture must contain a collection list")

    seen_ids: set[str] = set()
    for entry in collection:
        if not isinstance(entry, dict):
            raise ValueError("user collection entries must be objects")
        anime_id = entry.get("anime_id")
        if not isinstance(anime_id, str) or not anime_id.strip():
            raise ValueError("user collection entries require an anime_id")
        if anime_id in seen_ids:
            raise ValueError("duplicate anime IDs in user collection")
        seen_ids.add(anime_id)
        if anime_id not in anime_by_id:
            raise ValueError("user collection references an unknown anime ID")

        status = entry.get("status")
        if not isinstance(status, str) or status not in _COLLECTION_STATUSES:
            raise ValueError("user collection contains an unknown status")
        if "rating" not in entry:
            raise ValueError("user collection entries require a rating")
        rating = entry["rating"]
        if rating is not None and (not _is_non_negative_int(rating) or rating > 10):
            raise ValueError("user collection ratings must be between 0 and 10")
        watched = entry.get("episodes_watched")
        if not _is_non_negative_int(watched):
            raise ValueError("user collection progress must be a non-negative integer")
        total = anime_by_id[anime_id].get("episodes")
        if total is not None and watched > total:
            raise ValueError("user collection progress exceeds the anime episode count")


def _validate_calendar_fixture(calendar: dict[str, Any]) -> None:
    events = calendar.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict) for event in events
    ):
        raise ValueError("calendar anime fixture must contain an events list")


def _validate_search_snapshots(
    snapshots: dict[str, Any],
    anime_by_id: dict[str, dict[str, Any]],
) -> None:
    results = snapshots.get("results")
    if not isinstance(results, dict):
        raise ValueError("search-snapshots anime fixture must contain results")
    if any(anime_id not in anime_by_id for anime_id in results):
        raise ValueError("search-snapshots fixture references an unknown anime ID")
    if any(not isinstance(items, list) for items in results.values()):
        raise ValueError("search-snapshots results must be lists")


def _is_non_negative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _freeze_fixture_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_fixture_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_fixture_value(item) for item in value)
    return value
