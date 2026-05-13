from datetime import datetime

from app.memory.stores.json_store import JsonStore

SHORT_TERM_DIR = "data/memory/short_term"


class ShortTermMemory:
    def __init__(self, max_messages: int = 10):
        self.store = JsonStore(SHORT_TERM_DIR)
        self.max_messages = max_messages

    async def get(self, thread_id: str) -> list[dict]:
        data = await self.store.read(f"{thread_id}.json")
        return data.get("messages", [])

    async def add(self, thread_id: str, role: str, content: str) -> None:
        now = datetime.utcnow().isoformat()
        existing = await self.store.read(f"{thread_id}.json")

        messages = existing.get("messages", [])
        messages.append({"role": role, "content": content, "timestamp": now})

        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages:]

        await self.store.write(f"{thread_id}.json", {
            "thread_id": thread_id,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
            "max_messages": self.max_messages,
            "messages": messages,
        })

    async def add_pair(self, thread_id: str, user_msg: str, assistant_msg: str) -> None:
        await self.add(thread_id, "user", user_msg)
        await self.add(thread_id, "assistant", assistant_msg)

    async def clear(self, thread_id: str) -> None:
        await self.store.delete(f"{thread_id}.json")

    async def get_last_n(self, thread_id: str, n: int = 10) -> list[dict]:
        messages = await self.get(thread_id)
        return messages[-n:] if len(messages) > n else messages
