"""RecommendationAgent — MULTI-AGENT-001 Step 03.

Structured recommendation specialist using RecommendationCapability
and MemoryService.  Enforces candidate and model-call budgets.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_CANDIDATES = 20
_MAX_MODEL_CALLS = 3


class RecommendationAgent(BaseAgent):
    """Produces anime recommendations using capability + memory.

    Depends on ``RecommendationCapability`` and ``MemoryService``
    abstractions — never imports repositories or domain services directly.
    """

    def __init__(
        self,
        recommendation_capability: Any,
        anime_capability: Any = None,
        memory_service: Any = None,
        response_generator: Any = None,
        max_candidates: int = _MAX_CANDIDATES,
        max_model_calls: int = _MAX_MODEL_CALLS,
    ) -> None:
        self._capability = recommendation_capability
        self._anime_capability = anime_capability
        self._memory = memory_service
        self._response_generator = response_generator
        self.max_candidates = max_candidates
        self.max_model_calls = max_model_calls

    async def execute(self, task: Any) -> dict[str, Any]:
        """Generate a structured recommendation for the given task."""
        goal = task.goal if hasattr(task, "goal") else str(task)
        metadata = getattr(task, "metadata", None) or {}
        collections = self._resolve_collections(task)
        if self._response_generator is not None and self.max_model_calls < 1:
            return self._fallback("model_budget_exhausted")

        memory_context = None
        if self._memory is not None:
            memory_context = await self._memory.retrieve_context(
                metadata.get("thread_id", ""),
                goal,
                user_id=getattr(task, "user_id", None),
            )

        result = await self._capability.execute(
            "generate_profile",
            collections=collections,
            memory_context=memory_context,
        )

        if not result.get("success"):
            return self._fallback("capability_failed")

        profile = result.get("profile", {})
        candidates, candidate_search_failed = await self._select_candidates(profile)
        if candidate_search_failed:
            return self._fallback("candidate_search_failed")
        content = self._build_response(goal, candidates, profile)
        model_calls_used = 0
        if self._response_generator is not None:
            if model_calls_used >= self.max_model_calls:
                return self._fallback("model_budget_exhausted")
            model_calls_used += 1
            content = await self._response_generator.generate(
                goal,
                candidates,
                profile,
            )

        return {
            "role": "assistant",
            "content": content,
            "candidates": candidates[: self.max_candidates],
            "evidence": {
                **result.get("evidence", {"source": "profile"}),
                "model_calls_used": model_calls_used,
            },
        }

    async def plan(self, task: Any) -> dict[str, Any]:
        return {
            "goal": getattr(task, "goal", ""),
            "steps": [
                "Retrieve user profile via RecommendationCapability",
                "Select top candidates",
                "Generate recommendation response",
            ],
            "estimated_tools": ["generate_user_profile_tool"],
        }

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        return {
            "goal_achieved": bool(result.get("candidates")),
            "observations": [
                f"Candidates: {len(result.get('candidates', []))}",
                f"Evidence source: {result.get('evidence', {}).get('source', 'unknown')}",
            ],
        }

    # -- internal helpers -------------------------------------------------

    def _resolve_collections(self, task: Any) -> list[dict[str, Any]]:
        """Extract collections from task metadata or memory."""
        metadata = getattr(task, "metadata", None) or {}
        return metadata.get("collections", [])

    async def _select_candidates(
        self,
        profile: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], bool]:
        """Pick top-N candidates from the profile, within budget."""
        profile_candidates = profile.get("candidates", [])
        if profile_candidates:
            return profile_candidates[: self.max_candidates], False
        if self._anime_capability is None:
            return [], False
        tastes = list(
            profile.get("llm_summary", {}).get("taste_dictionary", {}).keys()
        )
        if not tastes:
            return [], False
        search = await self._anime_capability.execute(
            "search",
            keyword=tastes[0],
            tags=tastes[:3],
            limit=self.max_candidates,
        )
        if not search.get("success"):
            return [], True
        watched_ids = set(profile.get("watched_ids", []))
        return (
            [
                candidate
                for candidate in search.get("results", [])
                if candidate.get("id") not in watched_ids
            ][: self.max_candidates],
            False,
        )

    @staticmethod
    def _fallback(reason: str) -> dict[str, Any]:
        content = {
            "candidate_search_failed": "推荐服务暂时不可用，请稍后重试。",
        }.get(reason, "我暂时无法为你生成推荐。请先给一些看过作品评分吧。")
        return {
            "role": "assistant",
            "content": content,
            "candidates": [],
            "evidence": {"source": "fallback", "reason": reason},
        }

    def _build_response(
        self,
        goal: str,
        candidates: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> str:
        if not candidates:
            return "我暂时没有足够的信息来推荐。再多看些作品并评分吧！"

        lines = ["根据你的偏好，我推荐以下作品：\n"]
        for i, cand in enumerate(candidates[:5], 1):
            subject = cand.get("subject") if isinstance(cand, dict) else None
            name = cand.get("name") or cand.get("label")
            if not name and isinstance(subject, dict):
                name = subject.get("name") or subject.get("title")
            name = name or f"作品{i}"
            score = cand.get("score", cand.get("rate", cand.get("value", "")))
            lines.append(f"  {i}. {name}  (匹配度: {score})")
        lines.append("\n可以告诉我你的想法，或继续探索其他类型。")
        return "\n".join(lines)
