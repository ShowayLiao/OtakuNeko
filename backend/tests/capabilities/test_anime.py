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


def test_calendar_and_linked_user_actions_are_discoverable():
    actions = {action.name: action for action in AnimeCapability().actions()}

    assert actions["get_bangumi_calendar"].requires_auth is False
    assert actions["get_bangumi_calendar"].max_output_fields == 8192
    assert actions["get_detail_batch"].requires_auth is False
    assert actions["get_detail_batch"].input_schema["properties"]["subject_ids"]["maxItems"] == 5
    assert actions["get_bangumi_user_info"].requires_auth is True
    assert "username" not in actions["get_bangumi_user_info"].input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_batch_anime_details_uses_subject_ids(monkeypatch):
    async def fake_details(subject_ids):
        return {
            "details": [{"id": subject_ids[0], "name": "Anime", "summary": "summary"}],
            "failed_subject_ids": [],
        }

    monkeypatch.setattr("app.capabilities.anime.get_bangumi_subject_details", fake_details)

    result = await AnimeCapability().execute("get_detail_batch", subject_ids=[123])

    assert result["success"] is True
    assert result["details"][0]["id"] == 123


@pytest.mark.asyncio
async def test_linked_user_info_uses_trusted_user_identity(monkeypatch):
    captured = {}

    async def fake_info(username):
        captured["username"] = username
        return {"username": username, "id": 7, "sign": "public"}

    monkeypatch.setattr("app.capabilities.anime.get_bangumi_user_info", fake_info)
    result = await AnimeCapability().execute(
        "get_bangumi_user_info",
        user=type("User", (), {"bangumi_name": "linked-name", "username": "local"})(),
        user_id=3,
    )

    assert result["success"] is True
    assert captured["username"] == "linked-name"


@pytest.mark.asyncio
async def test_linked_user_info_does_not_fallback_to_local_username(monkeypatch):
    async def unexpected_lookup(username):
        pytest.fail(f"unexpected Bangumi lookup for local username: {username}")

    monkeypatch.setattr("app.capabilities.anime.get_bangumi_user_info", unexpected_lookup)
    result = await AnimeCapability().execute(
        "get_bangumi_user_info",
        user=type("User", (), {"bangumi_name": None, "username": "local"})(),
        user_id=3,
    )

    assert result["success"] is False
    assert result["error_type"] == "not_configured"
