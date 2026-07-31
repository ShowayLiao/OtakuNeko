"""RecommendationAgent — MULTI-AGENT-001 Step 03.

Structured recommendation specialist using RecommendationCapability
and MemoryService.  Enforces candidate and model-call budgets.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.core.logging import get_logger
from app.trace import TraceEventType
from app.trace.recorder import current_trace_recorder

logger = get_logger(__name__)

_MAX_CANDIDATES = 20
_MAX_MODEL_CALLS = 3
_MAX_PREFERENCE_TAGS = 3
_RECALL_MULTIPLIER = 5
_MIN_RECALL_LIMIT = 20


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
        policy = metadata.get("policy") or {}
        allowed = policy.get("allowed_capabilities", ())
        if "allowed_capabilities" in policy and "recommendation.generate_profile" not in allowed:
            return self._fallback("policy_denied")
        max_model_calls = min(
            self.max_model_calls, int(policy.get("max_model_calls", self.max_model_calls))
        )
        collections = self._resolve_collections(task)
        if self._response_generator is not None and max_model_calls < 1:
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
        candidates, empty_reason, search_stats = await self._select_candidates(profile)
        if empty_reason:
            return self._fallback(empty_reason, search_stats)
        selected_candidates = candidates[: self.max_candidates]
        structured_data = {
            "goal": goal,
            "profile": self._public_profile_summary(profile),
            "candidates": self._public_candidates(selected_candidates),
            "presentation": {
                "type": "recommendation_report",
                "requirements": [
                    "总结用户偏好",
                    "逐项说明每部作品的匹配理由",
                    "引用匹配标签或评分依据",
                    "说明明确反感标签冲突（如有）",
                    "给出下一步探索方向",
                ],
            },
        }
        content = self._build_response(goal, candidates, profile)
        model_calls_used = 0
        if self._response_generator is not None:
            if model_calls_used >= max_model_calls:
                return self._fallback("model_budget_exhausted")
            model_calls_used += 1
            content = await self._response_generator.generate(
                goal,
                candidates,
                profile,
            )

        return {
            "kind": "subagent",
            "name": "recommendation",
            "status": "completed",
            "role": "assistant",
            "content": content,
            "data": structured_data,
            "candidates": selected_candidates,
            "evidence": {
                **result.get("evidence", {"source": "profile"}),
                "model_calls_used": model_calls_used,
                "candidate_search": search_stats,
            },
        }

    async def plan(self, task: Any) -> dict[str, Any]:
        return {
            "goal": getattr(task, "goal", ""),
            "steps": [
                "Retrieve user profile via RecommendationCapability",
                "Select top candidates",
                "Return structured recommendation evidence",
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

    @staticmethod
    def _public_profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
        summary = profile.get("llm_summary", {}) or {}
        return {
            "total_rated": summary.get("total_rated", 0),
            "favorite_tags": list(summary.get("favorite_tags", []))[:20],
            "avoid_tags": list(summary.get("avoid_tags", []))[:20],
            "strong_avoid_tags": list(summary.get("strong_avoid_tags", []))[:20],
            "taste_dictionary": dict(list(summary.get("taste_dictionary", {}).items())[:20]),
            "tag_preferences": dict(list(summary.get("tag_preferences", {}).items())[:20]),
        }

    @staticmethod
    def _public_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        public: list[dict[str, Any]] = []
        allowed_keys = {
            "id",
            "name",
            "name_cn",
            "label",
            "summary",
            "score",
            "rate",
            "rating",
            "tags",
            "date",
            "platform",
            "subject",
        }
        for candidate in candidates:
            item = {
                key: value
                for key, value in candidate.items()
                if key in allowed_keys
            }
            if isinstance(item.get("summary"), str):
                item["summary"] = item["summary"][:1000]
            if isinstance(item.get("tags"), list):
                item["tags"] = item["tags"][:30]
            public.append(item)
        return public

    async def _select_candidates(
        self,
        profile: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str | None, dict[str, int]]:
        """Pick top-N candidates from the profile, within budget."""
        stats = {
            "preferred_tag_count": 0,
            "search_calls": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "raw_candidates": 0,
            "deduplicated_candidates": 0,
            "filtered_watched": 0,
            "filtered_strong_avoid": 0,
            "final_candidates": 0,
        }
        profile_candidates = profile.get("candidates", [])
        if profile_candidates:
            stats["final_candidates"] = min(len(profile_candidates), self.max_candidates)
            return profile_candidates[: self.max_candidates], None, stats
        if self._anime_capability is None:
            return [], None, stats
        summary = profile.get("llm_summary", {})
        favorite_tags = summary.get("favorite_tags")
        if favorite_tags is None:
            tastes = list(summary.get("taste_dictionary", {}).keys())
        else:
            tastes = list(favorite_tags)
        tastes = tastes[:_MAX_PREFERENCE_TAGS]
        stats["preferred_tag_count"] = len(tastes)
        if not tastes:
            self._record_candidate_search_stats(stats)
            return [], "cold_start", stats

        recall_limit = max(self.max_candidates * _RECALL_MULTIPLIER, _MIN_RECALL_LIMIT)
        raw_candidates: list[dict[str, Any]] = []
        for taste in tastes:
            stats["search_calls"] += 1
            search = await self._anime_capability.execute(
                "search",
                keyword="",
                tags=[taste],
                limit=recall_limit,
            )
            if not search.get("success"):
                stats["failed_searches"] += 1
                continue
            stats["successful_searches"] += 1
            results = search.get("results", []) or []
            stats["raw_candidates"] += len(results)
            raw_candidates.extend(results)

        if not stats["successful_searches"]:
            self._record_candidate_search_stats(stats)
            return [], "candidate_search_failed", stats
        if not raw_candidates:
            self._record_candidate_search_stats(stats)
            return [], "no_search_results", stats

        candidates: list[dict[str, Any]] = []
        seen_ids: set[Any] = set()
        for index, candidate in enumerate(raw_candidates):
            candidate_id = candidate.get("id")
            dedupe_key = candidate_id if candidate_id is not None else ("missing-id", index)
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            candidates.append(candidate)
        stats["deduplicated_candidates"] = len(candidates)

        watched_ids = set(profile.get("watched_ids", []))
        strong_avoid_tags = {
            str(tag) for tag in summary.get("strong_avoid_tags", []) if tag
        }
        filtered_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.get("id") in watched_ids:
                stats["filtered_watched"] += 1
                continue
            if self._has_avoided_tag(candidate, strong_avoid_tags):
                stats["filtered_strong_avoid"] += 1
                continue
            filtered_candidates.append(candidate)

        tag_preferences = summary.get("tag_preferences", {})
        soft_avoid_tags = {
            str(tag) for tag in summary.get("avoid_tags", []) if tag
        } - strong_avoid_tags
        filtered_candidates.sort(
            key=lambda candidate: self._candidate_sort_key(
                candidate,
                tag_preferences,
                soft_avoid_tags,
            ),
            reverse=True,
        )
        stats["final_candidates"] = min(len(filtered_candidates), self.max_candidates)
        if not filtered_candidates:
            self._record_candidate_search_stats(stats)
            return [], "no_unseen_safe_candidates", stats
        self._record_candidate_search_stats(stats)
        return filtered_candidates[: self.max_candidates], None, stats

    @staticmethod
    def _record_candidate_search_stats(stats: dict[str, int]) -> None:
        recorder = current_trace_recorder()
        if recorder is not None:
            recorder.record(
                TraceEventType.CAPABILITY_CALL,
                "recommendation.candidate_search",
                stats,
            )

    @classmethod
    def _candidate_sort_key(
        cls,
        candidate: dict[str, Any],
        tag_preferences: dict[str, dict[str, Any]],
        soft_avoid_tags: set[str],
    ) -> tuple[float, float, float]:
        candidate_tags = cls._candidate_tags(candidate)
        preference_score = sum(
            float(tag_preferences.get(tag, {}).get("preference_score", 0))
            for tag in candidate_tags
        )
        soft_penalty = sum(
            abs(float(tag_preferences.get(tag, {}).get("preference_delta", 0)))
            for tag in candidate_tags & soft_avoid_tags
        )
        quality_score = float(candidate.get("score") or 0)
        return preference_score - soft_penalty * 20, quality_score, -float(candidate.get("id") or 0)

    @staticmethod
    def _candidate_tags(candidate: dict[str, Any]) -> set[str]:
        raw_tags = candidate.get("tags") or []
        tags = set()
        for tag in raw_tags:
            name = tag.get("name") if isinstance(tag, dict) else tag
            if name:
                tags.add(str(name))
        return tags

    @staticmethod
    def _has_avoided_tag(candidate: dict[str, Any], avoid_tags: set[str]) -> bool:
        if not avoid_tags:
            return False
        raw_tags = candidate.get("tags")
        if not raw_tags:
            return False
        candidate_tags = RecommendationAgent._candidate_tags(candidate)
        return bool(candidate_tags & avoid_tags)

    @staticmethod
    def _fallback(reason: str, search_stats: dict[str, int] | None = None) -> dict[str, Any]:
        content = {
            "candidate_search_failed": "推荐服务暂时不可用，请稍后重试。",
            "no_search_results": "当前没有找到匹配的动画作品。",
            "no_unseen_safe_candidates": "当前没有找到既未看过、又避开明确反感标签的新作品。",
        }.get(reason, "我暂时无法为你生成推荐。请先给一些看过作品评分吧。")
        return {
            "kind": "subagent",
            "name": "recommendation",
            "status": "degraded",
            "role": "assistant",
            "content": content,
            "data": {"candidates": []},
            "candidates": [],
            "evidence": {
                "source": "fallback",
                "reason": reason,
                **({"candidate_search": search_stats} if search_stats else {}),
            },
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
