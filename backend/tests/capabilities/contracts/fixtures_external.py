"""Explicit successful examples for external capability actions.

Every external call is replaced at the dependency boundary. The registered
capabilities and their action handlers remain the production implementations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.capabilities import anime as anime_capability
from app.capabilities import media as media_capability
from app.capabilities import recommendation as recommendation_capability
from app.capabilities import system as system_capability
from app.schemas.bangumi import (
    AudienceFeedback,
    BangumiCalendar,
    BangumiCalendarDay,
    BangumiCalendarItem,
    CastInfo,
    LongReview,
    ShortComment,
    StaffInfo,
    SubjectDetail,
)
from .model import Case, Environment


async def _prepare_anime_search(env: Environment) -> None:
    async def search_subjects_advanced(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["keyword"] == "contract mystery anime"
        assert kwargs["subject_types"] == [2]
        assert kwargs["tags"] == ["Mystery"]
        assert kwargs["limit"] == 5
        env.calls.append("anime.search_subjects_advanced")
        return {
            "total": 1,
            "data": [
                {
                    "id": 501,
                    "name": "The Contract Case",
                    "name_cn": "契约测试",
                    "summary": "A detective follows a trail of clues.",
                    "rating": {"score": 8.7, "rank": 42},
                    "type": 2,
                    "air_date": "2026-04-01",
                    "images": {"common": "https://example.invalid/501.png"},
                    "tags": [{"name": "Mystery"}, {"name": "Investigation"}],
                }
            ],
        }

    env.monkeypatch.setattr(
        anime_capability, "search_subjects_advanced", search_subjects_advanced
    )


async def _prepare_anime_detail(env: Environment) -> None:
    async def fetch_subject_by_id(subject_id: int) -> SubjectDetail:
        assert subject_id == 501
        env.calls.append("anime.fetch_subject_by_id")
        return SubjectDetail(
            id=501,
            name="The Contract Case",
            name_cn="契约测试",
            summary="A detective follows a trail of clues.",
            score=8.7,
            rank=42,
            core_staff=[StaffInfo(name="Example Studio", role="Animation Studio")],
            main_cast=[
                CastInfo(
                    character_name="Aki",
                    role="主角",
                    cv_names=["Sample Voice Actor"],
                )
            ],
        )

    env.monkeypatch.setattr(
        anime_capability, "fetch_subject_by_id", fetch_subject_by_id
    )


async def _prepare_anime_detail_batch(env: Environment) -> None:
    async def get_bangumi_subject_details(subject_ids: list[int]) -> dict[str, Any]:
        assert subject_ids == [501, 502]
        env.calls.append("anime.get_bangumi_subject_details")
        return {
            "details": [
                {
                    "id": 501,
                    "name": "The Contract Case",
                    "summary": "A synthetic mystery.",
                },
                {
                    "id": 502,
                    "name": "The Second Case",
                    "summary": "A synthetic sequel.",
                },
            ],
            "failed_subject_ids": [],
        }

    env.monkeypatch.setattr(
        anime_capability, "get_bangumi_subject_details", get_bangumi_subject_details
    )


async def _prepare_anime_staff(env: Environment) -> None:
    async def get_staff_info(subject_id: int) -> list[StaffInfo]:
        assert subject_id == 501
        env.calls.append("anime.get_staff_info")
        return [StaffInfo(name="Example Studio", role="Animation Studio")]

    env.monkeypatch.setattr(anime_capability, "get_staff_info", get_staff_info)


async def _prepare_anime_cast(env: Environment) -> None:
    async def get_cast_info(subject_id: int) -> list[CastInfo]:
        assert subject_id == 501
        env.calls.append("anime.get_cast_info")
        return [
            CastInfo(
                character_name="Aki",
                role="主角",
                cv_names=["Sample Voice Actor"],
            )
        ]

    env.monkeypatch.setattr(anime_capability, "get_cast_info", get_cast_info)


async def _prepare_anime_reviews(env: Environment) -> None:
    async def get_audience_feedback(subject_id: int) -> AudienceFeedback:
        assert subject_id == 501
        env.calls.append("anime.get_audience_feedback")
        return AudienceFeedback(
            subject_id=501,
            comments=[ShortComment(content="A clever mystery.")],
            reviews=[
                LongReview(
                    title="A satisfying case",
                    summary="The clues resolve clearly.",
                )
            ],
        )

    env.monkeypatch.setattr(
        anime_capability, "get_audience_feedback", get_audience_feedback
    )


async def _prepare_anime_calendar(env: Environment) -> None:
    async def get_bangumi_calendar() -> BangumiCalendar:
        env.calls.append("anime.get_bangumi_calendar")
        return BangumiCalendar(
            root=[
                BangumiCalendarDay(
                    weekday={"id": 1, "en": "Monday", "cn": "星期一"},
                    items=[
                        BangumiCalendarItem(
                            id=501,
                            name="The Contract Case",
                            name_cn="契约测试",
                            air_date="2026-04-01",
                            air_weekday=1,
                            url=None,
                            type=None,
                            summary=None,
                            images=None,
                            rating=None,
                            collection=None,
                        )
                    ],
                )
            ]
        )

    env.monkeypatch.setattr(
        anime_capability, "get_bangumi_calendar", get_bangumi_calendar
    )


async def _prepare_anime_user_info(env: Environment) -> None:
    username = env.user.bangumi_name

    async def get_bangumi_user_info(requested_username: str) -> dict[str, Any]:
        assert requested_username == username
        assert requested_username == env.user.bangumi_name
        env.calls.append("anime.get_bangumi_user_info")
        return {
            "username": requested_username,
            "nickname": "Contract User",
            "id": 7001,
        }

    env.monkeypatch.setattr(
        anime_capability, "get_bangumi_user_info", get_bangumi_user_info
    )


def _recommendation_collections() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    return [
        {
            "rate": 9,
            "updated_at": now,
            "subject": {
                "id": 101,
                "tags": [{"name": "Adventure"}, {"name": "Mystery"}],
            },
        },
        {
            "rate": 9,
            "updated_at": now,
            "subject": {
                "id": 102,
                "tags": [{"name": "Adventure"}, {"name": "Mystery"}],
            },
        },
        {
            "rate": 9,
            "updated_at": now,
            "subject": {"id": 103, "tags": [{"name": "Adventure"}]},
        },
    ]


async def _prepare_recommendation(env: Environment) -> None:
    collections = _recommendation_collections()

    async def get_user_collections(db: Any, query: Any) -> SimpleNamespace:
        assert db is env.db
        assert query.user_id == env.user.id
        assert query.limit is None
        env.calls.append("recommendation.get_user_collections")
        return SimpleNamespace(items=collections)

    env.monkeypatch.setattr(
        recommendation_capability, "get_user_collections", get_user_collections
    )


class _FakeQBService:
    def __init__(self, env: Environment) -> None:
        self.env = env

    def get_rss_items(self) -> dict[str, Any]:
        self.env.calls.append("media.get_rss_items")
        return {
            "items": {
                "anime-feed": {
                    "uid": "anime-feed",
                    "url": "https://example.invalid/anime.xml",
                }
            }
        }

    def get_rss_rules(self) -> dict[str, Any]:
        self.env.calls.append("media.get_rss_rules")
        return {
            "rules": {
                "anime-rule": {
                    "enabled": True,
                    "mustContain": "The Contract Case",
                    "torrentParams": {"download_path": "private/provider/path"},
                }
            }
        }

    def add_rss_feed(self, url: str, name: str | None) -> dict[str, str]:
        assert url == "https://example.invalid/new-anime.xml"
        assert name == "New anime"
        self.env.calls.append("media.add_rss_feed")
        return {"status": "succeeded", "message": "Feed added."}

    def upsert_rss_feed(self, url: str, name: str | None) -> dict[str, str]:
        assert url == "https://example.invalid/existing-anime.xml"
        assert name == "Existing anime"
        self.env.calls.append("media.upsert_rss_feed")
        return {"status": "succeeded", "message": "Feed updated."}

    def remove_rss_item(self, item_path: str) -> dict[str, str]:
        assert item_path == "anime-feed"
        self.env.calls.append("media.remove_rss_item")
        return {"status": "succeeded", "message": "Feed removed."}

    def set_rss_rule(self, rule_name: str, rule: Any) -> dict[str, str]:
        assert rule_name == "anime-rule"
        assert rule.mustContain == "The Contract Case"
        self.env.calls.append("media.set_rss_rule")
        return {"status": "succeeded", "message": "Rule saved."}

    def remove_rss_rule(self, rule_name: str) -> dict[str, str]:
        assert rule_name == "anime-rule"
        self.env.calls.append("media.remove_rss_rule")
        return {"status": "succeeded", "message": "Rule removed."}


async def _prepare_media(env: Environment) -> None:
    settings = SimpleNamespace(
        ENABLE_QB_PROXY=True,
        QB_ALLOWED_USER_IDS=str(env.user.id),
        QB_HOST="http://fixture.invalid",
        QB_USERNAME="fixture-user",
    )

    def fixture_settings() -> SimpleNamespace:
        env.calls.append("media.fixture_settings")
        return settings

    env.monkeypatch.setattr(media_capability, "_settings", fixture_settings)
    env.monkeypatch.setattr(media_capability, "_new_qb", lambda: _FakeQBService(env))


async def _prepare_system_time(env: Environment) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> FixedDateTime:
            env.calls.append("system.datetime.now")
            return cls(2026, 1, 2, 3, 4, 5, tzinfo=tz)

    env.monkeypatch.setattr(system_capability, "datetime", FixedDateTime)


def _rule_arguments() -> dict[str, Any]:
    return {
        "affectedFeeds": ["anime-feed"],
        "assignedCategory": "anime",
        "enabled": True,
        "episodeFilter": "",
        "ignoreDays": 0,
        "mustContain": "The Contract Case",
        "mustNotContain": "",
        "previouslyMatchedEpisodes": [],
        "priority": 1,
        "savePath": "anime",
        "smartFilter": False,
        "useRegex": False,
    }


CASES: dict[tuple[str, str], Case] = {
    ("search_anime_advanced", "v1"): Case(
        arguments={
            "keyword": "contract mystery anime",
            "subject_types": [2],
            "tags": ["Mystery"],
            "limit": 5,
        },
        expected={
            "total": 1,
            "results": [
                {
                    "id": 501,
                    "name": "The Contract Case",
                    "score": 8.7,
                    "tags": ["Mystery", "Investigation"],
                }
            ],
        },
        prepare=_prepare_anime_search,
    ),
    ("get_anime_info", "v1"): Case(
        arguments={"subject_id": 501},
        expected={
            "id": 501,
            "name": "The Contract Case",
            "core_staff": [{"name": "Example Studio", "role": "Animation Studio"}],
            "main_cast": [
                {
                    "character_name": "Aki",
                    "role": "主角",
                    "cv_names": ["Sample Voice Actor"],
                }
            ],
        },
        prepare=_prepare_anime_detail,
    ),
    ("get_anime_info_batch", "v1"): Case(
        arguments={"subject_ids": [501, 502]},
        expected={
            "details": [
                {"id": 501, "name": "The Contract Case"},
                {"id": 502, "name": "The Second Case"},
            ],
            "failed_subject_ids": [],
        },
        prepare=_prepare_anime_detail_batch,
    ),
    ("get_anime_staff", "v1"): Case(
        arguments={"subject_id": 501},
        expected={"staff": [{"name": "Example Studio", "role": "Animation Studio"}]},
        prepare=_prepare_anime_staff,
    ),
    ("get_anime_cast", "v1"): Case(
        arguments={"subject_id": 501},
        expected={
            "cast": [
                {
                    "character_name": "Aki",
                    "role": "主角",
                    "cv_names": ["Sample Voice Actor"],
                }
            ]
        },
        prepare=_prepare_anime_cast,
    ),
    ("fetch_audience_reviews", "v1"): Case(
        arguments={"subject_id": 501},
        expected={
            "subject_id": 501,
            "comments": [{"content": "A clever mystery."}],
            "reviews": [
                {
                    "title": "A satisfying case",
                    "summary": "The clues resolve clearly.",
                }
            ],
        },
        prepare=_prepare_anime_reviews,
    ),
    ("get_bangumi_calendar", "v1"): Case(
        arguments={},
        expected={
            "calendar": [
                {
                    "weekday": {"id": 1, "en": "Monday", "cn": "星期一"},
                    "items": [{"id": 501, "name": "The Contract Case"}],
                }
            ]
        },
        prepare=_prepare_anime_calendar,
    ),
    ("get_bangumi_user_info", "v1"): Case(
        arguments={},
        expected={
            "user": {
                "username": "contract-bangumi",
                "nickname": "Contract User",
                "id": 7001,
            }
        },
        prepare=_prepare_anime_user_info,
    ),
    ("generate_user_profile_tool", "v1"): Case(
        arguments={},
        expected={
            "profile": {
                "llm_summary": {
                    "total_rated": 3,
                    "taste_dictionary": {
                        "Adventure": [3, 9.0],
                        "Mystery": [2, 9.0],
                    },
                },
                "watched_ids": [101, 102, 103],
            },
            "evidence": {"source": "profile", "total_rated": 3},
        },
        prepare=_prepare_recommendation,
    ),
    ("analyse_taste", "v1"): Case(
        arguments={},
        expected={
            "quadrants": {"core_favorites": ["Adventure", "Mystery"]},
            "evidence": {"source": "profile", "total_tags_analysed": 2},
        },
        prepare=_prepare_recommendation,
    ),
    ("library_status", "v1"): Case(
        arguments={},
        expected={"configured": True, "provider": "qbittorrent"},
        prepare=_prepare_media,
    ),
    ("list_rss_feeds", "v1"): Case(
        arguments={},
        expected={
            "feeds": {
                "anime-feed": {
                    "uid": "anime-feed",
                    "url": "https://example.invalid/anime.xml",
                }
            },
            "configured": True,
        },
        prepare=_prepare_media,
    ),
    ("list_rss_rules", "v1"): Case(
        arguments={},
        expected={
            "rules": {
                "anime-rule": {
                    "enabled": True,
                    "mustContain": "The Contract Case",
                }
            }
        },
        prepare=_prepare_media,
    ),
    ("add_rss_feed", "v1"): Case(
        arguments={
            "url": "https://example.invalid/new-anime.xml",
            "name": "New anime",
            "idempotency_key": "contract-add-feed-v1",
        },
        expected={
            "operation": {"status": "succeeded", "message": "Feed added."},
        },
        prepare=_prepare_media,
    ),
    ("upsert_rss_feed", "v1"): Case(
        arguments={
            "url": "https://example.invalid/existing-anime.xml",
            "name": "Existing anime",
            "idempotency_key": "contract-upsert-feed-v1",
        },
        expected={
            "operation": {"status": "succeeded", "message": "Feed updated."},
        },
        prepare=_prepare_media,
    ),
    ("remove_rss_feed", "v1"): Case(
        arguments={
            "item_path": "anime-feed",
            "idempotency_key": "contract-remove-feed-v1",
        },
        expected={
            "operation": {"status": "succeeded", "message": "Feed removed."},
        },
        prepare=_prepare_media,
    ),
    ("set_rss_rule", "v1"): Case(
        arguments={
            "rule_name": "anime-rule",
            "rule": _rule_arguments(),
            "idempotency_key": "contract-set-rule-v1",
        },
        expected={
            "operation": {"status": "succeeded", "message": "Rule saved."},
        },
        prepare=_prepare_media,
    ),
    ("remove_rss_rule", "v1"): Case(
        arguments={
            "rule_name": "anime-rule",
            "idempotency_key": "contract-remove-rule-v1",
        },
        expected={
            "operation": {"status": "succeeded", "message": "Rule removed."},
        },
        prepare=_prepare_media,
    ),
    ("get_current_time", "v1"): Case(
        arguments={},
        expected={
            "current_date": "2026-01-02",
            "current_year": 2026,
            "weekday": 4,
            "weekday_cn": "星期五",
            "timezone": "本地时间",
        },
        prepare=_prepare_system_time,
    ),
}
