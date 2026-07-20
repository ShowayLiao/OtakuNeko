"""Tests for CAPABILITY-002: RecommendationCapability."""

import pytest

from app.capabilities.recommendation import RecommendationCapability


@pytest.fixture
def capability():
    return RecommendationCapability()


class TestRecommendationCapability:
    def test_name_is_recommendation(self, capability):
        assert capability.name == "recommendation"

    def test_actions_are_registered(self, capability):
        names = {a.name for a in capability.actions()}
        assert "generate_profile" in names
        assert "analyse_taste" in names

    @pytest.mark.asyncio
    async def test_empty_history_returns_deterministic_fallback(self, capability):
        result = await capability.execute("generate_profile", collections=[])
        assert result["success"] is True
        assert result.get("evidence", {}).get("source") == "empty_history"

    @pytest.mark.asyncio
    async def test_generate_profile_with_minimal_data(self, capability):
        """Smoke test: a single entry should not crash the pipeline."""
        minimal = [
            {
                "rate": 8,
                "subject": {
                    "id": 1,
                    "name": "Test Anime",
                    "tags": [{"name": "测试", "count": 1}],
                },
            },
        ]
        result = await capability.execute("generate_profile", collections=minimal)
        assert result["success"] is True
        assert "profile" in result

    @pytest.mark.asyncio
    async def test_analyse_taste_empty_history(self, capability):
        result = await capability.execute("analyse_taste", collections=[])
        assert result["success"] is True
        quadrants = result.get("quadrants", {})
        assert quadrants["core_favorites"] == []
        assert quadrants["time_killers"] == []
        assert quadrants["avoid_tags"] == []

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, capability):
        result = await capability.execute("bogus")
        assert result["success"] is False
        assert "Unknown action" in result["error"]

    @pytest.mark.asyncio
    async def test_service_failure_returns_typed_error(self, capability, monkeypatch):
        def raise_err(*args, **kwargs):
            raise RuntimeError("profile service down")

        monkeypatch.setattr(
            "app.capabilities.recommendation.generate_user_profile",
            raise_err,
        )
        result = await capability.execute("generate_profile", collections=[{}])
        assert result["success"] is False
        assert result["error_type"] == "internal"
