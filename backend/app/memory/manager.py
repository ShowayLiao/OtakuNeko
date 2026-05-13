from dataclasses import dataclass, field

from app.memory.short_term import ShortTermMemory
from app.memory.long_term import LongTermMemory


@dataclass
class MemoryContext:
    short_term_messages: list[dict] = field(default_factory=list)
    long_term_facts: list[dict] = field(default_factory=list)
    summary: str = ""


class MemoryManager:
    def __init__(self, api_key: str, base_url: str,
                 short_term_max: int = 10, long_term_max: int = 500):
        self.short_term = ShortTermMemory(max_messages=short_term_max)
        self.long_term = LongTermMemory(api_key=api_key, base_url=base_url,
                                        max_facts=long_term_max)

    async def load_context(self, thread_id: str, current_query: str,
                           top_k: int = 5) -> MemoryContext:
        short = await self.short_term.get_last_n(thread_id, n=10)
        long_facts = await self.long_term.retrieve(thread_id, current_query, top_k=top_k)

        parts = []
        if long_facts:
            parts.append("[长期记忆] 相关历史信息：")
            for f in long_facts:
                parts.append(f"- {f['content']}")
        if short:
            parts.append("[近期对话]")
            for m in short[-6:]:
                role_label = "用户" if m["role"] == "user" else "AI"
                parts.append(f"- [{role_label}] {m['content'][:200]}")

        return MemoryContext(
            short_term_messages=short,
            long_term_facts=long_facts,
            summary="\n".join(parts) if parts else "",
        )

    async def save_turn(self, thread_id: str, user_msg: str,
                        assistant_msg: str) -> None:
        await self.short_term.add_pair(thread_id, user_msg, assistant_msg)

    async def extract_and_store_facts(self, thread_id: str) -> int:
        messages = await self.short_term.get_last_n(thread_id, n=20)
        if len(messages) < 4:
            return 0

        conv_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in messages
        )
        system_prompt = (
            "请从以下对话中提取关于用户的重要信息（偏好、习惯、个人信息、重要决策），"
            "每条信息简洁概括（一句话）。不要提取琐碎的闲聊内容。\n"
            "只返回 JSON 格式：{\"facts\": [{\"content\": \"...\", \"importance\": 0.8}]}"
        )

        try:
            response = await self.long_term.vector.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conv_text},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            import json
            result = json.loads(response.choices[0].message.content or "{}")
            facts = result.get("facts", [])

            count = 0
            for fact in facts:
                content = fact.get("content", "")
                importance = float(fact.get("importance", 0.5))
                if content:
                    fact_id = await self.long_term.add_fact(
                        thread_id, content, importance=importance
                    )
                    if fact_id:
                        count += 1
            return count
        except Exception:
            return 0
