"""Fact extraction via LLM.

Wraps the existing fact-extraction logic from MemoryManager in a
standalone extractor that can be used independently of the service
or repository layers.
"""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.memory.interfaces import MemoryExtractor
from app.memory.types import MemorySourceType
from app.core.logging import get_logger

logger = get_logger(__name__)

_EXTRACTION_SYSTEM_PROMPT = (
    "请从以下对话中提取关于用户的重要信息（偏好、习惯、个人信息、重要决策），"
    "每条信息简洁概括（一句话）。不要提取琐碎的闲聊内容。\n"
    "只返回 JSON 格式：{\"facts\": [{\"content\": \"...\", \"importance\": 0.8}]}"
)


class LLMFactExtractor(MemoryExtractor):
    """Uses an LLM to extract structured facts from conversation messages."""

    def __init__(self, api_key: str, base_url: str, model: str = "gpt-3.5-turbo") -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def extract(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run fact extraction over the given messages."""
        user_messages = [
            message for message in messages
            if message.get("role") in ("human", "user")
        ]
        if not user_messages:
            return []

        conv_text = "\n".join(
            f"{'用户' if m['role'] in ('human', 'user') else 'AI'}: {m['content']}"
            for m in user_messages
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": conv_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            result = json.loads(response.choices[0].message.content or "{}")
            facts = result.get("facts", [])

            validated: list[dict[str, Any]] = []
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                forbidden = {
                    "instruction", "instructions", "credential",
                    "credentials", "approval", "approve", "policy",
                    "system", "tool", "external", "prompt",
                }
                if any(key.lower() in forbidden for key in fact):
                    continue
                content = fact.get("content", "")
                if content:
                    content = str(content).strip()
                    if _looks_like_untrusted_instruction(content):
                        continue
                    try:
                        importance = min(
                            1.0, max(0.0, float(fact.get("importance", 0.5)))
                        )
                    except (TypeError, ValueError):
                        importance = 0.5
                    try:
                        confidence = min(
                            1.0, max(0.0, float(fact.get("confidence", 0.5)))
                        )
                    except (TypeError, ValueError):
                        confidence = 0.5
                    validated.append(
                        {
                            "content": content[:2000],
                            "importance": importance,
                            "source_type": MemorySourceType.USER.value,
                            "source_id": "user-statement",
                            "confidence": confidence,
                            "verified": False,
                        }
                    )
            return validated
        except Exception:
            logger.exception("fact_extraction_failed")
            return []


def _looks_like_untrusted_instruction(content: str) -> bool:
    lowered = content.lower()
    markers = (
        "ignore previous",
        "ignore system",
        "ignore policy",
        "system prompt",
        "api key",
        "access token",
        "忽略系统",
        "系统策略",
        "泄露",
    )
    return any(marker in lowered for marker in markers)
