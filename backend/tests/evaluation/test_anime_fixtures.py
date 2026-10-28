"""Tests for isolated synthetic anime benchmark fixtures."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.evaluation.anime_fixtures import (
    collection_snapshot,
    load_anime_fixture_set,
    seed_anime_fixture,
)
from app.capabilities.recommendation import RecommendationCapability
from app.models import Collection, CollectionStatus, Subject, User


FIXTURE_DIR = (
    Path(__file__).resolve().parents[3] / "otakuneko-benchmark-v1" / "fixtures"
)


def test_loads_valid_v1_fixture_set_and_is_frozen() -> None:
    fixture_set = load_anime_fixture_set(FIXTURE_DIR)

    assert fixture_set.fixture_dir == FIXTURE_DIR
    assert fixture_set.user["schema_version"] == 1
    assert fixture_set.catalog["synthetic"] is True
    assert len(fixture_set.user["collection"]) == 11
    with pytest.raises(FrozenInstanceError):
        fixture_set.fixture_dir = Path("elsewhere")
    with pytest.raises(TypeError):
        fixture_set.user["collection"][0]["status"] = "planned"


def test_rejects_catalog_without_synthetic_marker(tmp_path: Path) -> None:
    _copy_fixtures(tmp_path)
    catalog = _read_json(tmp_path / "catalog.synthetic.json")
    catalog["synthetic"] = False
    _write_json(tmp_path / "catalog.synthetic.json", catalog)

    with pytest.raises(ValueError, match="catalog.*synthetic"):
        load_anime_fixture_set(tmp_path)


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "catalog.synthetic.json",
            lambda payload: payload["anime"].append(payload["anime"][0].copy()),
            "duplicate.*anime",
        ),
        (
            "user.synthetic.json",
            lambda payload: payload["collection"].append(
                payload["collection"][0].copy()
            ),
            "duplicate.*collection",
        ),
        (
            "user.synthetic.json",
            lambda payload: payload["collection"][0].update(anime_id="AC999"),
            "unknown.*anime",
        ),
        (
            "user.synthetic.json",
            lambda payload: payload["collection"][0].update(status="mystery"),
            "unknown.*status",
        ),
    ],
)
def test_rejects_invalid_fixture_references_and_ids(
    tmp_path: Path,
    filename: str,
    mutate,
    message: str,
) -> None:
    _copy_fixtures(tmp_path)
    payload = _read_json(tmp_path / filename)
    mutate(payload)
    _write_json(tmp_path / filename, payload)

    with pytest.raises(ValueError, match=message):
        load_anime_fixture_set(tmp_path)


def test_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    _copy_fixtures(tmp_path)
    user = _read_json(tmp_path / "user.synthetic.json")
    user["schema_version"] = 2
    _write_json(tmp_path / "user.synthetic.json", user)

    with pytest.raises(ValueError, match="schema_version"):
        load_anime_fixture_set(tmp_path)


@pytest.mark.asyncio
async def test_seed_and_snapshot_use_trusted_user_and_persisted_collection_state(
    tmp_path: Path,
) -> None:
    _copy_fixtures(tmp_path)
    user_fixture = _read_json(tmp_path / "user.synthetic.json")
    user_fixture["collection"][0]["status"] = "on_hold"
    _write_json(tmp_path / "user.synthetic.json", user_fixture)
    fixture_set = load_anime_fixture_set(tmp_path)
    test_user_id = 501
    other_user_id = 502
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    User(id=test_user_id, username="fixture-test-user"),
                    User(id=other_user_id, username="fixture-other-user"),
                ]
            )
            await session.flush()

            await seed_anime_fixture(
                session,
                test_user_id=test_user_id,
                fixture_set=fixture_set,
            )
            assert session.in_transaction()

            profile_result = await RecommendationCapability().execute(
                "generate_profile",
                db=session,
                user_id=test_user_id,
            )
            profile = profile_result["profile"]
            taste_tags = profile["llm_summary"]["taste_dictionary"]
            assert profile_result["success"] is True
            assert taste_tags
            expected_tags = {
                tag
                for anime in fixture_set.catalog["anime"]
                if anime["id"] in {"AC001", "AC002", "AC003", "AC005", "AC011"}
                for tag in anime["tags"]
            }
            assert set(taste_tags) & expected_tags

            collection_count = await session.scalar(
                select(func.count())
                .select_from(Collection)
                .where(Collection.user_id == test_user_id)
            )
            subjects = (await session.scalars(select(Subject))).all()
            assert collection_count == 11
            assert {subject.source_id for subject in subjects} == {
                item["id"] for item in fixture_set.catalog["anime"]
            }
            assert all(subject.source == "bangumi" for subject in subjects)
            assert all(int(subject.type) == 2 for subject in subjects)
            assert all(subject.tags for subject in subjects)

            seeded_collections = (
                await session.scalars(
                    select(Collection).where(Collection.user_id == test_user_id)
                )
            ).all()
            status_codes = {
                "planned": CollectionStatus.WISH,
                "complete": CollectionStatus.COLLECT,
                "watching": CollectionStatus.DO,
                "on_hold": CollectionStatus.ON_HOLD,
                "dropped": CollectionStatus.DROPPED,
            }
            expected_collection = {
                item["anime_id"]: (
                    int(status_codes[item["status"]]),
                    item["rating"],
                    item["episodes_watched"],
                )
                for item in fixture_set.user["collection"]
            }
            assert {
                item.source_id: (
                    int(item.type),
                    item.rate,
                    item.ep_status,
                )
                for item in seeded_collections
            } == expected_collection

            other_user_collection = Collection(
                user_id=other_user_id,
                source="bangumi",
                source_id="AC007",
                type=CollectionStatus.COLLECT,
                rate=1,
                ep_status=1,
                subject_type=2,
            )
            other_user_only_collection = Collection(
                user_id=other_user_id,
                source="bangumi",
                source_id="OTHER-USER",
                type=CollectionStatus.WISH,
                rate=None,
                ep_status=0,
                subject_type=2,
            )
            session.add_all([other_user_collection, other_user_only_collection])
            await session.flush()

            persisted = await session.scalar(
                select(Collection).where(
                    Collection.user_id == test_user_id,
                    Collection.source_id == "AC007",
                )
            )
            assert persisted is not None
            assert int(persisted.type) == int(CollectionStatus.DO)
            persisted.type = CollectionStatus.ON_HOLD
            persisted.rate = 6
            persisted.ep_status = 5
            await session.flush()

            snapshot = await collection_snapshot(session, user_id=test_user_id)

        assert snapshot["AC007"] == {
            "type": int(CollectionStatus.ON_HOLD),
            "rate": 6,
            "episodes_watched": 5,
        }
        assert len(snapshot) == 11
        assert snapshot["AC007"]["rate"] != 1
        assert "OTHER-USER" not in snapshot
    finally:
        await engine.dispose()


def _copy_fixtures(target_dir: Path) -> None:
    for filename in (
        "user.synthetic.json",
        "catalog.synthetic.json",
        "calendar.synthetic.json",
        "search-snapshots.synthetic.json",
    ):
        (target_dir / filename).write_bytes((FIXTURE_DIR / filename).read_bytes())


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
