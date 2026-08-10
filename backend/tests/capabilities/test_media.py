"""Tests for CAPABILITY-002: MediaCapability."""

import pytest

from app.capabilities.media import MediaCapability


@pytest.fixture
def capability():
    return MediaCapability()


class TestMediaCapability:
    def test_name_is_media(self, capability):
        assert capability.name == "media"

    def test_actions_registered(self, capability):
        names = {a.name for a in capability.actions()}
        assert "library_status" in names
        assert "list_rss_feeds" in names
        assert "list_rss_rules" in names
        assert "add_rss_feed" in names
        assert "upsert_rss_feed" in names
        assert "remove_rss_feed" in names
        assert "set_rss_rule" in names
        assert "remove_rss_rule" in names

    def test_write_actions_require_auth(self, capability):
        actions = {a.name: a for a in capability.actions()}
        for name in (
            "add_rss_feed", "upsert_rss_feed", "remove_rss_feed",
            "set_rss_rule", "remove_rss_rule",
        ):
            assert actions[name].requires_auth is True
            assert actions[name].is_side_effect is True
            assert actions[name].idempotency_mode == "required"

    @pytest.mark.asyncio
    async def test_library_status_returns_configured_field(self, capability):
        result = await capability.execute("library_status")
        assert result["success"] is True
        assert "configured" in result

    @pytest.mark.asyncio
    async def test_list_rss_feeds_returns_not_configured(self, capability):
        result = await capability.execute("list_rss_feeds")
        assert result["success"] is True
        assert result.get("configured") is False

    @pytest.mark.asyncio
    async def test_add_rss_feed_returns_not_configured(self, capability):
        result = await capability.execute("add_rss_feed", url="http://example.com/feed")
        assert result["success"] is False
        assert result.get("error_type") == "not_configured"

    @pytest.mark.asyncio
    async def test_rss_list_uses_provider_and_returns_bounded_fields(self, capability, monkeypatch):
        class FakeQB:
            def get_rss_items(self):
                return type("Items", (), {"items": {"feed": {"uid": "1", "url": "https://example.com"}}})()

        monkeypatch.setattr("app.capabilities.media.QBService", FakeQB)
        monkeypatch.setattr("app.capabilities.media._qb_access_allowed", lambda user_id: True)
        monkeypatch.setattr("app.capabilities.media._provider_configured", lambda: True)

        result = await capability.execute("list_rss_feeds", user_id=1)

        assert result["success"] is True
        assert result["feeds"]["feed"] == {"uid": "1", "url": "https://example.com"}

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, capability):
        result = await capability.execute("bogus")
        assert result["success"] is False
