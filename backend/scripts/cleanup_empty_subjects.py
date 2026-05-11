import asyncio
import sys
sys.path.insert(0, '.')

from sqlmodel import select, delete
from app.db.database import engine, AsyncSessionLocal
from app.models import Subject


async def inspect():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subject).where(
                (Subject.name == '') | (Subject.name.is_(None))
            )
        )
        dirty = result.scalars().all()
        print(f"\n脏数据数量: {len(dirty)}")
        for s in dirty:
            print(f"  id={s.id}  source={s.source}  source_id={s.source_id}  name='{s.name}' type={s.type}")
        return dirty


async def cleanup():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Subject).where(
                (Subject.name == '') | (Subject.name.is_(None))
            )
        )
        await session.commit()
        print(f"\n已删除 {result.rowcount} 条脏数据。")


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    if mode == "delete":
        confirm = input("确认删除以上脏数据？输入 yes 继续: ")
        if confirm.lower() == "yes":
            await cleanup()
        else:
            print("已取消。")
    else:
        await inspect()
        print('\n确认无误后执行: uv run python scripts/cleanup_empty_subjects.py delete')

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
