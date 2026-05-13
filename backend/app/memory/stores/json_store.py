from pathlib import Path
import asyncio
import json
import os

import aiofiles


class JsonStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, file_name: str) -> asyncio.Lock:
        if file_name not in self._locks:
            self._locks[file_name] = asyncio.Lock()
        return self._locks[file_name]

    async def read(self, file_name: str) -> dict:
        path = self.base_dir / file_name
        if not path.exists():
            return {}
        async with self._get_lock(file_name):
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content) if content.strip() else {}

    async def write(self, file_name: str, data: dict) -> None:
        path = self.base_dir / file_name
        tmp_path = path.with_suffix(".tmp")
        async with self._get_lock(file_name):
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            os.replace(tmp_path, path)

    async def delete(self, file_name: str) -> bool:
        path = self.base_dir / file_name
        if not path.exists():
            return False
        async with self._get_lock(file_name):
            path.unlink()
            return True

    async def exists(self, file_name: str) -> bool:
        return (self.base_dir / file_name).exists()
