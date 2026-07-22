import pytest

from app.capabilities.anime import AnimeCapability


@pytest.mark.asyncio
async def test_search_defaults_to_anime_subject_type(monkeypatch):
    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return {"total": 1, "data": [{"id": 1, "name": "Test", "summary": "summary"}]}

    monkeypatch.setattr("app.capabilities.anime.search_subjects_advanced", fake_search)

    result = await AnimeCapability().execute("search", keyword="test")

    assert result["success"] is True
    assert captured["subject_types"] == [2]
    assert result["results"][0]["id"] == 1


@pytest.mark.asyncio
async def test_search_preserves_explicit_filters(monkeypatch):
    captured = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return {"total": 0, "data": []}

    monkeypatch.setattr("app.capabilities.anime.search_subjects_advanced", fake_search)

    await AnimeCapability().execute(
        "search",
        keyword="test",
        subject_types=[1],
        tags=["original"],
        rating_ranges=[">=8"],
        air_date_ranges=[">=2024-01-01"],
        limit=5,
        offset=10,
    )

    assert captured == {
        "keyword": "test",
        "subject_types": [1],
        "tags": ["original"],
        "rating_ranges": [">=8"],
        "air_date_ranges": [">=2024-01-01"],
        "limit": 5,
        "offset": 10,
    }


@pytest.mark.asyncio
async def test_unknown_action_returns_typed_error():
    result = await AnimeCapability().execute("bogus")
    assert result["success"] is False
    assert result["error_type"] == "invalid_action"


@pytest.mark.asyncio
async def test_service_failure_returns_typed_error(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("bangumi down")

    monkeypatch.setattr("app.capabilities.anime.fetch_subject_by_id", fail)

    result = await AnimeCapability().execute("get_detail", subject_id=999)
    assert result["success"] is False
    assert result["error_type"] == "internal"
