# 服务层操作手册

## 目录

1. [服务结构说明](#服务结构说明)
2. [Bangumi 相关服务](#bangumi-相关服务)
   - [BangumiClient](#bangumiclient)
   - [BangumiDataSyncService](#bangumidatasyncservice)
   - [BangumiService](#bangumiservice)
3. [收藏相关服务](#收藏相关服务)
   - [CollectionService](#collectionservice)
4. [用户相关服务](#用户相关服务)
   - [UserService](#userservice)
5. [条目相关服务](#条目相关服务)
   - [SubjectService](#subjectservice)
6. [排班相关服务](#排班相关服务)
   - [ScheduleService](#scheduleservice)
7. [统计相关服务](#统计相关服务)
   - [StatsService](#statsservice)
8. [其他服务](#其他服务)
   - [DoubanService](#doubanservice)
   - [QBService](#qbservice)
   - [UserProfileService](#userprofileservice)
9. [使用示例](#使用示例)
10. [最佳实践](#最佳实践)

## 服务结构说明

本项目的服务层（Services）负责封装业务逻辑，处理与外部API的交互，以及协调不同仓库之间的操作。服务文件组织结构如下：

- `__init__.py` - 服务导出文件
- `bangumi_client.py` - Bangumi API 客户端
- `bangumi_data_sync.py` - Bangumi 数据同步服务
- `bangumi_service.py` - Bangumi 业务逻辑服务
- `collection_service.py` - 收藏相关业务逻辑服务
- `douban_service.py` - 豆瓣数据同步服务
- `qb_service.py` - qBittorrent API 服务
- `schedule_service.py` - 排班相关业务逻辑服务
- `stats_service.py` - 统计相关业务逻辑服务
- `subject_service.py` - 条目相关业务逻辑服务
- `user_profile_service.py` - 用户画像生成服务
- `user_service.py` - 用户相关业务逻辑服务

## Bangumi 相关服务

### BangumiClient

**功能**：封装与 Bangumi API 的交互，提供获取用户收藏、条目详情、搜索条目、用户信息和日历信息的功能。

**主要方法**：
- `get_user_collections` - 获取用户的收藏数据
- `get_subject_detail` - 获取单个条目的详细信息
- `search_subjects` - 搜索条目
- `get_user_info` - 获取用户信息
- `get_calendar` - 获取每日放送信息
- `get_persons_raw` - 获取条目的制作人员信息

**使用示例**：

```python
from app.services.bangumi_client import bangumi_client

# 获取用户收藏
collections = await bangumi_client.get_user_collections("username", subject_type=2)

# 获取条目详情
subject_detail = await bangumi_client.get_subject_detail(12345)

# 搜索条目
search_results = await bangumi_client.search_subjects("测试", subject_type=2)

# 获取用户信息
user_info = await bangumi_client.get_user_info("username")

# 获取日历信息
calendar = await bangumi_client.get_calendar()
```

### BangumiDataSyncService

**功能**：从 bangumi-data 同步番剧放送信息，并提供查询放送时间的功能。

**主要方法**：
- `fetch_and_sync_recent_data` - 同步最近的番剧放送信息
- `get_air_time` - 获取番剧的放送时间
- `get_air_time_batch` - 批量获取番剧的放送时间

**使用示例**：

```python
from app.services.bangumi_data_sync import BangumiDataSyncService

# 同步番剧放送信息
synced_count = await BangumiDataSyncService.fetch_and_sync_recent_data(db)

# 获取番剧的放送时间
air_time_info = await BangumiDataSyncService.get_air_time(db, 12345)

# 批量获取番剧的放送时间
air_time_dict = await BangumiDataSyncService.get_air_time_batch(db, [12345, 67890])
```

### BangumiService

**功能**：提供与 Bangumi 相关的业务逻辑，如同步用户收藏、同步条目详情、获取用户信息和日历信息。

**主要方法**：
- `fetch_subject_by_id` - 获取条目详情，并自动清洗 Staff 数据
- `sync_user_collections` - 同步用户的 Bangumi 收藏数据到本地数据库
- `sync_subject_detail` - 从 Bangumi API 同步单个条目的详细信息到本地数据库
- `get_bangumi_user_info` - 获取 Bangumi 用户信息
- `get_bangumi_calendar` - 获取 Bangumi 每日放送信息

**使用示例**：

```python
from app.services.bangumi_service import sync_user_collections, get_bangumi_calendar, fetch_subject_by_id

# 同步用户收藏
synced_count = await sync_user_collections(user, db)

# 获取 Bangumi 日历信息
calendar = await get_bangumi_calendar()

# 获取条目详情
subject_detail = await fetch_subject_by_id(12345)
```

## 收藏相关服务

### CollectionService

**功能**：处理收藏相关的业务逻辑，如创建、更新、删除收藏，以及批量操作和导入功能。

**主要方法**：
- `create_collection` - 创建单个收藏记录
- `get_collection` - 获取单个收藏记录
- `update_collection` - 更新用户的收藏信息
- `delete_collection` - 删除收藏记录
- `get_user_collections` - 获取用户的收藏列表
- `search_collections` - 根据关键词搜索收藏记录
- `upsert_collection` - 更新或添加收藏
- `batch_upsert_collections` - 批量更新或添加收藏
- `import_json_collections` - 导入JSON格式的收藏数据到数据库

**使用示例**：

```python
from app.services.collection_service import create_collection, get_user_collections, upsert_collection
from app.schemas.collection import CollectionCreate, CollectionSearchBase

# 创建收藏
collection = await create_collection(db, CollectionCreate(
    user_id=1,
    source="bangumi",
    source_id="12345",
    type=3,  # 在看
    rate=8
))

# 获取用户收藏列表
collections = await get_user_collections(db, CollectionSearchBase(
    user_id=1,
    skip=0,
    limit=20
))

# 更新或添加收藏
updated_collection = await upsert_collection(db, 1, data={
    "collection": {
        "source": "bangumi",
        "source_id": "12345",
        "type": 3,
        "rate": 9
    }
})
```

## 用户相关服务

### UserService

**功能**：处理用户相关的业务逻辑，如创建、更新、删除用户，以及登录功能。

**主要方法**：
- `create_user` - 创建新用户
- `get_user_by_id` - 根据ID获取用户
- `get_user_by_username` - 根据用户名获取用户
- `get_user_by_bangumi_id` - 根据Bangumi ID获取用户
- `get_all_users` - 获取所有用户
- `update_user` - 更新用户信息
- `delete_user` - 删除用户
- `login_user` - 用户登录服务

**使用示例**：

```python
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserLogin

# 创建用户
user = await UserService.create_user(db, UserCreate(
    username="test_user",
    avatar_url="https://example.com/avatar.jpg"
))

# 用户登录
logged_in_user = await UserService.login_user(db, UserLogin(
    username="test_user",
    avatar_url="https://example.com/avatar.jpg"
))
```

## 条目相关服务

### SubjectService

**功能**：处理条目相关的业务逻辑，如创建、更新、删除条目，以及搜索和同步功能。

**主要方法**：
- `create_subject` - 创建新条目
- `get_subject_by_source` - 根据数据源和ID获取条目
- `update_subject` - 更新条目
- `batch_update_subjects` - 批量更新条目
- `batch_upsert_subjects` - 批量 Upsert 条目
- `delete_subject` - 删除条目
- `get_all_subjects` - 获取所有条目
- `search_subject_by_name` - 基于名称的宽泛搜索
- `search_subject_cloud` - 调用 Bangumi API 进行搜索
- `search_mixed` - 混合搜索服务：并行搜索 + 结果合并
- `sync_subject_air_time` - 同步番剧放送时间

**使用示例**：

```python
from app.services.subject_service import create_subject, search_mixed, sync_subject_air_time
from app.schemas.subject import SubjectCreate, SubjectSearchBase

# 创建条目
subject = await create_subject(db, SubjectCreate(
    source="bangumi",
    source_id="12345",
    type=2,  # 动画
    name="Test Anime",
    name_cn="测试动画"
), user_id=1)

# 混合搜索
results = await search_mixed(db, SubjectSearchBase(
    keyword="测试",
    type=2,
    skip=0,
    limit=20,
    user_id=1
))

# 同步番剧放送时间
success = await sync_subject_air_time(db, "12345")
```

## 排班相关服务

### ScheduleService

**功能**：处理排班相关的业务逻辑，如创建、更新、删除排班，以及同步 Bangumi 日历数据。

**主要方法**：
- `get_user_schedules` - 获取用户的所有排班记录
- `get_unified_user_schedules` - 获取用户的所有排班记录，附带关联的条目和收藏信息
- `create_schedule` - 为用户创建新的排班记录
- `update_schedule` - 更新用户的排班记录
- `delete_schedule` - 删除用户的排班记录
- `get_schedules_by_day` - 获取用户指定星期的排班记录
- `upsert_schedule` - Upsert 排班记录（更新或插入）
- `bulk_upsert_schedules` - 批量 Upsert 排班记录
- `sync_bangumi_calendar` - 同步 Bangumi 日历数据
- `delete_all_schedules` - 删除当前用户的所有排班记录

**使用示例**：

```python
from app.services.schedule_service import ScheduleService
from app.schemas.schedule import ScheduleCreate

# 创建排班
schedule = await ScheduleService.create_schedule(db, 1, ScheduleCreate(
    source="bangumi",
    source_id="12345",
    day_of_week=1,  # 周一
    start_time="19:00",
    watch_day=1,
    watch_time="20:00"
))

# 获取用户排班列表
schedules = await ScheduleService.get_user_schedules(db, 1)

# 同步 Bangumi 日历数据
synced_count = await ScheduleService.sync_bangumi_calendar(db, 1)
```

## 统计相关服务

### StatsService

**功能**：提供用户收藏统计数据的功能。

**主要方法**：
- `get_user_stats` - 获取用户的收藏统计数据

**使用示例**：

```python
from app.services.stats_service import get_user_stats

# 获取用户统计数据
stats = await get_user_stats(1, db)
print(f"用户收藏统计: 动画={stats.anime}, 书籍={stats.books}, 音乐={stats.music}, 游戏={stats.games}, 三次元={stats.real}, 总计={stats.total}")
```

## 其他服务

### DoubanService

**功能**：同步用户的豆瓣收藏数据到本地数据库。

**主要方法**：
- `sync_user_collections_douban` - 同步用户的豆瓣收藏数据到本地数据库

**使用示例**：

```python
from app.services.douban_service import sync_user_collections_douban

# 同步豆瓣收藏数据
douban_data = [/* 豆瓣数据 */]
synced_count = await sync_user_collections_douban(1, db, douban_data)
```

### QBService

**功能**：封装了与 qBittorrent API 的交互，提供 RSS 订阅管理和自动下载规则设置的功能。

**主要方法**：
- `get_rss_items` - 获取所有 RSS 订阅项
- `add_rss_feed` - 添加 RSS 订阅源
- `upsert_rss_feed` - Upsert RSS 订阅源
- `remove_rss_item` - 删除 RSS 订阅项
- `set_rss_rule` - 设置 RSS 自动下载规则
- `remove_rss_rule` - 删除 RSS 自动下载规则
- `get_rss_rules` - 获取所有 RSS 自动下载规则

**使用示例**：

```python
from app.services.qb_service import QBService
from app.schemas.rss import RssRule

# 初始化 QBService
qb_service = QBService()

# 获取 RSS 订阅项
rss_items = qb_service.get_rss_items()

# 添加 RSS 订阅源
qb_service.add_rss_feed("https://example.com/rss", "测试订阅")

# 设置 RSS 自动下载规则
rule = RssRule(
    enabled=True,
    must_contain="测试",
    save_path="/downloads"
)
qb_service.set_rss_rule("测试规则", rule)
```

### UserProfileService

**功能**：基于「频次 + 平均分」的二维加权算法，从用户收藏数据生成用户画像。

**主要方法**：
- `generate_user_profile(collections)` — 输入 `List[CollectionSubject]`，输出三部分画像数据

**算法流程**：
1. 数据清洗 — 提取有效评分（跳过 rate=0/None）
2. 基础统计 — 每个 tag 的 count 和 total_score
3. 统计学修正 — 过滤 count<2 的小样本，计算平均分
4. 全景字典 — `{tag_name: [count, avg_score]}`，供大模型使用
5. 偏好指数 — 0-100 的 Affinity Score（雷达图用）
6. 图表数据 — radar/bar_count/bar_score 三种图表数据

**使用示例**：

```python
from app.services.user_profile_service import generate_user_profile

# collections: List[CollectionSubject]
profile = generate_user_profile(collections)
# → { llm_summary, chart_data, watched_ids }
```

## 使用示例

### 完整的使用示例

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import (
    UserService, CollectionService, SubjectService, 
    ScheduleService, BangumiService, stats_service
)
from app.schemas.user import UserCreate, UserLogin
from app.schemas.collection import CollectionCreate
from app.schemas.subject import SubjectCreate
from app.schemas.schedule import ScheduleCreate

async def example_usage(db: AsyncSession):
    # 1. 创建用户
    user = await UserService.create_user(db, UserCreate(
        username="test_user",
        avatar_url="https://example.com/avatar.jpg"
    ))
    print(f"Created user: {user.username}")
    
    # 2. 创建条目
    subject = await SubjectService.create_subject(db, SubjectCreate(
        source="bangumi",
        source_id="12345",
        type=2,  # 动画
        name="Test Anime",
        name_cn="测试动画"
    ), user.id)
    print(f"Created subject: {subject.name}")
    
    # 3. 创建收藏
    collection = await CollectionService.create_collection(db, CollectionCreate(
        user_id=user.id,
        source="bangumi",
        source_id="12345",
        type=3,  # 在看
        rate=8
    ))
    print(f"Created collection: {collection.id}")
    
    # 4. 创建排班
    schedule = await ScheduleService.create_schedule(db, user.id, ScheduleCreate(
        source="bangumi",
        source_id="12345",
        day_of_week=1,  # 周一
        start_time="19:00",
        watch_day=1,
        watch_time="20:00"
    ))
    print(f"Created schedule: {schedule.id}")
    
    # 5. 同步 Bangumi 收藏
    synced_count = await BangumiService.sync_user_collections(user, db)
    print(f"Synced {synced_count} collections from Bangumi")
    
    # 6. 获取用户统计数据
    stats = await stats_service.get_user_stats(user.id, db)
    print(f"User stats: anime={stats.anime}, total={stats.total}")
    
    # 7. 搜索条目
    search_results = await SubjectService.search_mixed(db, {
        "keyword": "测试",
        "type": 2,
        "skip": 0,
        "limit": 10,
        "user_id": user.id
    })
    print(f"Search results: {len(search_results.items)} items")
```

## 最佳实践

1. **异常处理**：所有服务方法都会抛出异常，使用时应进行适当的异常捕获和处理。

2. **事务管理**：服务方法内部已经处理了事务管理（commit/rollback），外部调用时无需再处理事务。

3. **参数验证**：使用 Pydantic 模型（如 UserCreate、CollectionCreate 等）进行参数验证，确保数据的合法性。

4. **缓存使用**：对于频繁访问的数据，服务层已经使用了缓存机制，如 Bangumi API 响应和用户统计数据。

5. **批量操作**：对于大量数据的操作，使用批量方法（如 batch_upsert）可以提高性能。

6. **数据一致性**：服务层会自动处理数据一致性，如清除相关缓存、更新关联数据等。

7. **日志记录**：所有服务方法都有详细的日志记录，便于调试和问题排查。

8. **API 调用限制**：对于外部 API（如 Bangumi API），服务层已经实现了请求延迟，避免请求过快被封禁。

9. **错误处理**：对于常见错误，如网络错误、数据解析错误等，服务层进行了专门的处理和日志记录。

10. **代码组织**：服务层按照功能进行了清晰的划分，便于维护和扩展。

11. **数据同步**：对于需要从外部 API 同步的数据，服务层提供了专门的同步方法，确保数据的及时性和准确性。

12. **搜索优化**：对于搜索功能，服务层实现了本地搜索和云端搜索的结合，提高搜索结果的完整性和准确性。