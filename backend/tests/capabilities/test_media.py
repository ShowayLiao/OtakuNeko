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
        assert "add_rss_feed" in names

    def test_write_actions_require_auth(self, capability):
        actions = {a.name: a for a in capability.actions()}
        assert actions["add_rss_feed"].requires_auth is True

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
    async def test_unknown_action_returns_error(self, capability):
        result = await capability.execute("bogus")
        assert result["success"] is False
