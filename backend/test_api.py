import asyncio
from app.db.database import get_session
from sqlmodel import select
from app.models.user import User
from app.models.collection import Collection
from app.models.subject import Subject

async def test_api():
    async for session in get_session():
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f'Users in database: {len(users)}')
        for u in users:
            print(f'  - {u.username} (ID: {u.id})')
        
        if users:
            for user in users:
                result = await session.execute(
                    select(Collection, Subject)
                    .where(Collection.user_id == user.id)
                    .where(Collection.subject_id == Subject.id)
                    .limit(1)
                )
                item = result.first()
                if item:
                    collection, subject = item
                    print(f'\nSample collection for user {user.username}:')
                    print(f'  Subject ID: {collection.subject_id}')
                    print(f'  Status (type): {collection.type.value}')
                    print(f'  Updated at: {collection.updated_at}')
                    print(f'  Updated at type: {type(collection.updated_at)}')
                    print(f'  Updated at ISO format: {collection.updated_at.isoformat()}')
                    print(f'  Subject name: {subject.name}')
                    break
        break

if __name__ == '__main__':
    asyncio.run(test_api())
