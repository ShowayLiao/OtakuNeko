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
        if len(messages) < 4:
            return []

        conv_text = "\n".join(
            f"{'用户' if m['role'] in ('human', 'user') else 'AI'}: {m['content']}"
            for m in messages
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
                content = fact.get("content", "")
                if content:
                    validated.append(
                        {
                            "content": str(content),
                            "importance": float(fact.get("importance", 0.5)),
                        }
                    )
            return validated
        except Exception:
            logger.exception("fact_extraction_failed")
            return []
