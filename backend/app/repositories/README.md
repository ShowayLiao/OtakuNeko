# 仓库操作手册

## 目录

1. [仓库结构说明](#仓库结构说明)
2. [SubjectRepo 操作指南](#subjectrepo-操作指南)
   - [创建/更新条目](#创建更新条目)
   - [查询条目](#查询条目)
   - [删除条目](#删除条目)
   - [批量操作](#批量操作)
3. [CollectionRepo 操作指南](#collectionrepo-操作指南)
   - [创建收藏](#创建收藏)
   - [查询收藏](#查询收藏)
   - [更新收藏](#更新收藏)
   - [删除收藏](#删除收藏)
   - [批量操作](#批量操作-1)
4. [UserRepo 操作指南](#userrepo-操作指南)
   - [创建用户](#创建用户)
   - [查询用户](#查询用户)
   - [更新用户](#更新用户)
   - [删除用户](#删除用户)
5. [ScheduleRepository 操作指南](#schedulerepository-操作指南)
   - [创建排班](#创建排班)
   - [查询排班](#查询排班)
   - [更新排班](#更新排班)
   - [删除排班](#删除排班)
   - [批量操作](#批量操作-2)
6. [使用示例](#使用示例)
7. [最佳实践](#最佳实践)

## 仓库结构说明

本项目的仓库层（Repositories）负责封装与数据库的交互操作，提供统一的数据访问接口。仓库文件组织结构如下：

- `__init__.py` - 仓库导出文件，定义了所有可导出的仓库类
- `subject_repo.py` - 条目相关的数据库操作
- `collection_repo.py` - 收藏相关的数据库操作
- `schedule_repo.py` - 排班相关的数据库操作
- `user_repo.py` - 用户相关的数据库操作

## SubjectRepo 操作指南

### 创建/更新条目

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo
from app.schemas.subject import SubjectCreate

async def create_or_update_subject(db: AsyncSession, subject_data: dict):
    # 创建 SubjectCreate 对象
    create_data = SubjectCreate(**subject_data)
    # 调用 create 方法（会自动判断是创建还是更新）
    subject = await SubjectRepo.create(db, create_data)
    return subject
```

### 查询条目

#### 根据来源和ID查询

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo
from app.schemas.subject import SubjectSearchByID

async def get_subject_by_source(db: AsyncSession, source: str, source_id: str, user_id: int = None):
    # 创建搜索条件
    search_data = SubjectSearchByID(source=source, source_id=source_id, user_id=user_id)
    # 调用查询方法
    result = await SubjectRepo.get_by_source(db, search_data)
    return result
```

#### 根据名称搜索

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo
from app.schemas.subject import SubjectSearchByName

async def search_subjects(db: AsyncSession, keyword: str, user_id: int = None, skip: int = 0, limit: int = 20):
    # 创建搜索条件
    search_data = SubjectSearchByName(keyword=keyword, user_id=user_id, skip=skip, limit=limit)
    # 调用搜索方法
    result = await SubjectRepo.search_by_name(db, search_data)
    return result
```

#### 获取所有条目

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo
from app.schemas.subject import SubjectSearchBase

async def get_all_subjects(db: AsyncSession, subject_type: int = None, skip: int = 0, limit: int = 100):
    # 创建搜索条件
    search_data = SubjectSearchBase(type=subject_type, skip=skip, limit=limit)
    # 调用查询方法
    result = await SubjectRepo.get_all(db, search_data)
    return result
```

### 删除条目

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo
from app.schemas.subject import SubjectSearchByID

async def delete_subject(db: AsyncSession, source: str, source_id: str):
    # 创建搜索条件
    search_data = SubjectSearchByID(source=source, source_id=source_id)
    # 调用删除方法
    result = await SubjectRepo.delete(db, search_data)
    return result
```

### 批量操作

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo
from app.schemas.subject import SubjectUpsertList, SubjectUpsert

async def batch_upsert_subjects(db: AsyncSession, subjects: list):
    # 准备批量数据
    upsert_items = [SubjectUpsert(**item) for item in subjects]
    # 创建批量操作对象
    data_list = SubjectUpsertList(items=upsert_items)
    # 调用批量操作方法
    count = await SubjectRepo.batch_upsert(db, data_list)
    return count
```

## CollectionRepo 操作指南

### 创建收藏

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo
from app.schemas.collection import CollectionCreate

async def create_collection(db: AsyncSession, collection_data: dict):
    # 创建 CollectionCreate 对象
    create_data = CollectionCreate(**collection_data)
    # 调用创建方法
    collection = await CollectionRepo.create(db, create_data)
    return collection
```

### 查询收藏

#### 根据用户和条目查询

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo
from app.schemas.collection import CollectionSearchByID

async def get_collection(db: AsyncSession, user_id: int, source: str, source_id: str):
    # 创建搜索条件
    search_data = CollectionSearchByID(user_id=user_id, source=source, source_id=source_id)
    # 调用查询方法
    result = await CollectionRepo.get_by_user_and_subject(db, search_data)
    return result
```

#### 获取用户的所有收藏

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo

async def get_user_collections(db: AsyncSession, user_id: int, subject_type: int = None, status: int = None, skip: int = 0, limit: int = 100, sort_by: str = 'updated_at'):
    # 调用查询方法
    result = await CollectionRepo.get_by_user(db, user_id, subject_type, status, skip, limit, sort_by)
    return result
```

#### 根据关键词搜索收藏

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo
from app.schemas.collection import CollectionSearchByName

async def search_collections(db: AsyncSession, user_id: int, keyword: str, status: int = None, skip: int = 0, limit: int = 20, sort_by: str = 'updated_at'):
    # 创建搜索条件
    search_data = CollectionSearchByName(user_id=user_id, keyword=keyword, status=status, skip=skip, limit=limit, sort_by=sort_by)
    # 调用搜索方法
    result = await CollectionRepo.search_by_keyword(db, search_data)
    return result
```

### 更新收藏

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo
from app.schemas.collection import CollectionUpdate

async def update_collection(db: AsyncSession, update_data: dict):
    # 创建 CollectionUpdate 对象
    collection_update = CollectionUpdate(**update_data)
    # 调用更新方法
    collection = await CollectionRepo.update(db, collection_update)
    return collection
```

### 删除收藏

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo
from app.schemas.collection import CollectionSearchByID

async def delete_collection(db: AsyncSession, user_id: int, source: str, source_id: str):
    # 创建搜索条件
    search_data = CollectionSearchByID(user_id=user_id, source=source, source_id=source_id)
    # 调用删除方法
    result = await CollectionRepo.delete(db, search_data)
    return result
```

### 批量操作

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import CollectionRepo
from app.schemas.collection import CollectionUpsertList, CollectionUpsert

async def batch_upsert_collections(db: AsyncSession, collections: list):
    # 准备批量数据
    upsert_items = [CollectionUpsert(**item) for item in collections]
    # 创建批量操作对象
    data_list = CollectionUpsertList(collections=upsert_items)
    # 调用批量操作方法
    await CollectionRepo.batch_upsert(db, data_list)
```

## UserRepo 操作指南

### 创建用户

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo
from app.schemas.user import UserCreate

async def create_user(db: AsyncSession, user_data: dict):
    # 创建 UserCreate 对象
    create_data = UserCreate(**user_data)
    # 调用创建方法
    user = await UserRepo.create(db, create_data)
    return user
```

### 查询用户

#### 根据ID查询

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo

async def get_user_by_id(db: AsyncSession, user_id: int):
    # 调用查询方法
    user = await UserRepo.get_by_id(db, user_id)
    return user
```

#### 根据用户名查询

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo

async def get_user_by_username(db: AsyncSession, username: str):
    # 调用查询方法
    user = await UserRepo.get_by_username(db, username)
    return user
```

#### 根据Bangumi ID查询

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo

async def get_user_by_bangumi_id(db: AsyncSession, bangumi_id: int):
    # 调用查询方法
    user = await UserRepo.get_by_bangumi_id(db, bangumi_id)
    return user
```

#### 获取所有用户

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo
from app.schemas.user import UserSearch

async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 100):
    # 创建搜索条件
    search_data = UserSearch(skip=skip, limit=limit)
    # 调用查询方法
    users = await UserRepo.get_all(db, search_data)
    return users
```

### 更新用户

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo
from app.schemas.user import UserUpdate

async def update_user(db: AsyncSession, user_id: int, update_data: dict):
    # 创建 UserUpdate 对象
    user_update = UserUpdate(**update_data)
    # 调用更新方法
    user = await UserRepo.update(db, user_id, user_update)
    return user
```

### 删除用户

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import UserRepo

async def delete_user(db: AsyncSession, user_id: int):
    # 调用删除方法
    result = await UserRepo.delete(db, user_id)
    return result
```

## ScheduleRepository 操作指南

### 创建排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import ScheduleCreate

async def create_schedule(db: AsyncSession, user_id: int, schedule_data: dict):
    # 创建 ScheduleCreate 对象
    create_data = ScheduleCreate(**schedule_data)
    # 调用创建方法
    schedule = await ScheduleRepository.create_for_user(db, user_id, create_data)
    return schedule
```

### 查询排班

#### 获取用户的所有排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository

async def get_user_schedules(db: AsyncSession, user_id: int):
    # 调用查询方法
    schedules = await ScheduleRepository.get_by_user(db, user_id)
    return schedules
```

#### 获取用户的统一排班（包含条目和收藏信息）

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository

async def get_user_unified_schedules(db: AsyncSession, user_id: int):
    # 调用查询方法
    schedules = await ScheduleRepository.get_unified_schedules_by_user(db, user_id)
    return schedules
```

#### 根据ID查询排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository

async def get_schedule_by_id(db: AsyncSession, schedule_id: int):
    # 调用查询方法
    schedule = await ScheduleRepository.get_by_id(db, schedule_id)
    return schedule
```

#### 获取用户指定星期的排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository

async def get_schedules_by_day(db: AsyncSession, user_id: int, day_of_week: int):
    # 调用查询方法
    schedules = await ScheduleRepository.get_by_day(db, user_id, day_of_week)
    return schedules
```

### 更新排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import ScheduleUpdate

async def update_schedule(db: AsyncSession, schedule_id: int, user_id: int, update_data: dict):
    # 创建 ScheduleUpdate 对象
    schedule_update = ScheduleUpdate(**update_data)
    # 调用更新方法
    schedule = await ScheduleRepository.update(db, schedule_id, user_id, schedule_update)
    return schedule
```

### 删除排班

#### 删除单个排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository

async def delete_schedule(db: AsyncSession, schedule_id: int, user_id: int):
    # 调用删除方法
    result = await ScheduleRepository.delete(db, schedule_id, user_id)
    return result
```

#### 删除用户的所有排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository

async def delete_all_user_schedules(db: AsyncSession, user_id: int):
    # 调用删除方法
    result = await ScheduleRepository.delete_all_by_user(db, user_id)
    return result
```

### 批量操作

#### 批量 Upsert 排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import ScheduleUpsertList, ScheduleUpsert

async def batch_upsert_schedules(db: AsyncSession, user_id: int, schedules: list):
    # 准备批量数据
    upsert_items = [ScheduleUpsert(**item) for item in schedules]
    # 创建批量操作对象
    data_list = ScheduleUpsertList(items=upsert_items)
    # 调用批量操作方法
    count = await ScheduleRepository.batch_upsert(db, user_id, data_list)
    return count
```

#### 单个 Upsert 排班

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import ScheduleUpsert

async def upsert_schedule(db: AsyncSession, user_id: int, schedule_data: dict):
    # 创建 ScheduleUpsert 对象
    upsert_data = ScheduleUpsert(**schedule_data)
    # 调用 Upsert 方法
    schedule = await ScheduleRepository.upsert(db, user_id, upsert_data)
    return schedule
```

## 使用示例

### 完整的使用示例

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import SubjectRepo, CollectionRepo, UserRepo
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.subject import SubjectCreate, SubjectSearchByID
from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionSearchByID
from app.schemas.user import UserCreate, UserUpdate
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate

async def example_usage(db: AsyncSession):
    # 1. 创建用户
    user_data = {
        "username": "test_user",
        "avatar_url": "https://example.com/avatar.jpg",
        "bangumi_id": 12345,
        "bangumi_name": "test_bangumi_user"
    }
    user = await UserRepo.create(db, UserCreate(**user_data))
    print(f"Created user: {user.username}")
    
    # 2. 创建或更新条目
    subject_data = {
        "source": "bangumi",
        "source_id": "12345",
        "type": 2,  # 动画
        "name": "Test Anime",
        "name_cn": "测试动画",
        "summary": "这是一个测试动画",
        "date": "2023-01-01",
        "platform": "TV"
    }
    subject = await SubjectRepo.create(db, SubjectCreate(**subject_data))
    print(f"Created/Updated subject: {subject.name}")
    
    # 3. 创建收藏
    collection_data = {
        "user_id": user.id,
        "source": "bangumi",
        "source_id": "12345",
        "type": 3,  # 在看
        "rate": 8,
        "comment": "非常好看"
    }
    collection = await CollectionRepo.create(db, CollectionCreate(**collection_data))
    print(f"Created collection: {collection.id}")
    
    # 4. 创建排班
    schedule_data = {
        "source": "bangumi",
        "source_id": "12345",
        "day_of_week": 1,  # 周一
        "start_time": "19:00",
        "watch_day": 1,  # 周一
        "watch_time": "20:00",
        "duration": 1,
        "watch_type": 4  # 新番
    }
    schedule = await ScheduleRepository.create_for_user(db, user.id, ScheduleCreate(**schedule_data))
    print(f"Created schedule: {schedule.id}")
    
    # 5. 查询用户的所有收藏
    collections = await CollectionRepo.get_by_user(db, user.id)
    print(f"User has {len(collections.items)} collections")
    
    # 6. 查询用户的所有排班
    schedules = await ScheduleRepository.get_by_user(db, user.id)
    print(f"User has {len(schedules)} schedules")
    
    # 7. 更新收藏
    update_data = {
        "user_id": user.id,
        "source": "bangumi",
        "source_id": "12345",
        "type": 2,  # 看过
        "rate": 9
    }
    updated_collection = await CollectionRepo.update(db, CollectionUpdate(**update_data))
    print(f"Updated collection: {updated_collection.id}, status: {updated_collection.type}")
    
    # 8. 更新排班
    schedule_update_data = {
        "watch_time": "21:00"
    }
    updated_schedule = await ScheduleRepository.update(db, schedule.id, user.id, ScheduleUpdate(**schedule_update_data))
    print(f"Updated schedule: {updated_schedule.id}, watch_time: {updated_schedule.watch_time}")
    
    # 9. 删除收藏
    delete_result = await CollectionRepo.delete(db, CollectionSearchByID(user_id=user.id, source="bangumi", source_id="12345"))
    print(f"Deleted collection: {delete_result}")
    
    # 10. 删除排班
    delete_schedule_result = await ScheduleRepository.delete(db, schedule.id, user.id)
    print(f"Deleted schedule: {delete_schedule_result}")
```

## 最佳实践

1. **异常处理**：所有仓库方法都会抛出 SQLAlchemyError 异常，使用时应进行适当的异常捕获和处理。

2. **事务管理**：仓库方法内部已经处理了事务管理（commit/rollback），外部调用时无需再处理事务。

3. **参数验证**：使用 Pydantic 模型（如 SubjectCreate、CollectionUpdate 等）进行参数验证，确保数据的合法性。

4. **批量操作**：对于大量数据的操作，使用批量方法（如 batch_upsert）可以提高性能。

5. **缓存清理**：仓库方法会自动清理相关的缓存，确保数据的一致性。

6. **分页查询**：对于列表查询，使用 skip 和 limit 参数进行分页，避免一次性加载大量数据。

7. **排序**：使用 sort_by 参数指定排序字段，优化查询结果的展示。

8. **搜索优化**：使用关键词搜索时，注意关键词的长度和复杂度，避免性能问题。

9. **索引利用**：仓库方法已经针对常用查询条件建立了索引，使用时应尽量利用这些索引。

10. **异步操作**：所有仓库方法都是异步的，使用时应配合 async/await 语法。

11. **用户权限验证**：对于 ScheduleRepository，所有操作都需要验证 user_id，确保用户只能操作自己的数据。

12. **数据一致性**：使用唯一约束确保数据的一致性，如用户对同一来源的同一条目只有一条收藏记录。

13. **数据清洗**：在批量操作中，对数据进行清洗和结构统一，确保数据的合法性和一致性。

14. **日志记录**：所有仓库方法都有详细的日志记录，便于调试和问题排查。

15. **错误处理**：对于常见错误，如数据完整性错误，进行专门的处理和日志记录。