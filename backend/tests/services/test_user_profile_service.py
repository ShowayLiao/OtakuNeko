from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.user_profile_service import generate_user_profile


AS_OF = datetime(2026, 7, 31, tzinfo=timezone.utc)


def rated_item(
    score: int,
    *,
    tags: list[str] | None = None,
    days_ago: int = 0,
    subject_id: int = 1,
) -> SimpleNamespace:
    subject = SimpleNamespace(
        id=subject_id,
        source_id=str(subject_id),
        tags=[{"name": tag} for tag in (tags or [])],
    )
    return SimpleNamespace(
        subject=subject,
        rate=score,
        updated_at=AS_OF - timedelta(days=days_ago),
    )


def preference_items() -> list[SimpleNamespace]:
    items: list[SimpleNamespace] = []
    subject_id = 1
    for score in (9, 9):
        items.append(rated_item(score, tags=["喜欢"], subject_id=subject_id))
        subject_id += 1
    for score in (5, 5):
        items.append(rated_item(score, tags=["雷区"], subject_id=subject_id))
        subject_id += 1
    for score in (7, 7):
        items.append(rated_item(score, tags=["中性"], subject_id=subject_id))
        subject_id += 1
    return items


def test_profile_shrinks_personal_baseline_toward_neutral_prior():
    profile = generate_user_profile(
        [rated_item(10, subject_id=1)],
        as_of=AS_OF,
    )

    assert profile["llm_summary"]["rating_baseline"] == pytest.approx(7.5)


def test_recent_rating_has_more_influence_than_old_rating():
    profile = generate_user_profile(
        [
            rated_item(10, days_ago=0, subject_id=1),
            rated_item(2, days_ago=365, subject_id=2),
        ],
        as_of=AS_OF,
    )

    assert profile["llm_summary"]["rating_baseline"] > 7.0


def test_tags_are_classified_by_centered_preference():
    profile = generate_user_profile(preference_items(), as_of=AS_OF)
    summary = profile["llm_summary"]

    assert "喜欢" in summary["favorite_tags"]
    assert "雷区" in summary["avoid_tags"]
    assert "中性" not in summary["favorite_tags"]
    assert "中性" not in summary["avoid_tags"]


def test_legacy_profile_fields_remain_available():
    profile = generate_user_profile(preference_items(), as_of=AS_OF)
    summary = profile["llm_summary"]
    chart_data = profile["chart_data"]

    assert {"total_rated", "taste_dictionary"} <= summary.keys()
    assert {"radar", "bar_count", "bar_score"} <= chart_data.keys()
    assert summary["taste_dictionary"]["喜欢"][0] == 2
