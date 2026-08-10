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
        assert "collections" not in capability.actions()[0].input_schema.get("required", [])

    @pytest.mark.asyncio
    async def test_trusted_collection_source_overrides_public_collection_argument(
        self, capability, monkeypatch
    ):
        captured = {}

        async def fake_collections(db, request):
            captured.update(
                db=db,
                user_id=request.user_id,
                limit=request.limit,
            )
            return type("Result", (), {"items": [{"rate": 9}]})()

        def fake_profile(collections):
            captured["collections"] = collections
            return {"llm_summary": {"total_rated": len(collections)}}

        monkeypatch.setattr(
            "app.capabilities.recommendation.get_user_collections", fake_collections
        )
        monkeypatch.setattr(
            "app.capabilities.recommendation.generate_user_profile", fake_profile
        )

        result = await capability.execute(
            "generate_profile",
            db="trusted-db",
            user_id=11,
            collections=[{"rate": 1}],
        )

        assert result["success"] is True
        assert captured == {
            "db": "trusted-db",
            "user_id": 11,
            "limit": None,
            "collections": [{"rate": 9}],
        }

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
                    "name": "Test Anime 1",
                    "tags": [{"name": "测试", "count": 1}],
                },
            },
            {
                "rate": 9,
                "subject": {
                    "id": 2,
                    "name": "Test Anime 2",
                    "tags": [{"name": "测试", "count": 1}],
                },
            },
        ]
        result = await capability.execute("generate_profile", collections=minimal)
        assert result["success"] is True
        assert "profile" in result
        assert result["profile"]["llm_summary"]["total_rated"] == 2
        assert result["profile"]["watched_ids"] == [1, 2]

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
