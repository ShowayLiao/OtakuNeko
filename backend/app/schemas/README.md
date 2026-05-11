# Schemas 模块 — Pydantic 数据验证层

## 模块简介

使用 **Pydantic v2** 定义所有 API 请求/响应的数据结构（DTO）。
提供数据验证、类型检查、以及 Bangumi API / 豆瓣 API 原始 JSON → 内部 Schema 的格式转换适配器。

## 文件结构说明

```
schemas/
├── __init__.py        # 导出常用 Schema
├── agent.py           # Agent 聊天请求/消息
├── bangumi.py         # Bangumi API 响应结构（SubjectDetail, Calendar 等）
├── collection.py      # 收藏 Schema（CRUD + 含关联条目）
├── dashboard.py       # 仪表盘统计
├── rss.py             # qBittorrent RSS 规则
├── schedule.py        # 番剧排班 Schema
├── shared.py          # 公共基类（BaseList, SearchBase）
├── subject.py         # 条目 Schema（CRUD + 搜索）
├── user.py            # 用户 Schema
└── adaptersV2.py      # 数据格式适配器（Bangumi JSON ⇄ 内部 Schema）
```

### adaptersV2.py — 数据格式适配器（核心） ([源码](adaptersV2.py))

这是整个 schemas 模块中**最大最关键的转换层**，提供 7 个转换函数：

| 函数 | 输入 | 输出 | 用途 |
|------|------|------|------|
| `bangumi_subject_to_subjectlist` | Bangumi 条目 JSON | `SubjectUpsertList` | 同步 Bangumi 条目到本地 |
| `bangumi_collection_to_subjectlist` | Bangumi 收藏 JSON | `SubjectUpsertList` | 从收藏中提取条目 |
| `bangumi_collection_to_collectionlist` | Bangumi 收藏 JSON | `CollectionUpsertList` | 同步收藏到本地 |
| `douban_to_bangumi_list` | 豆瓣 JSON | Bangumi 格式 JSON | 豆瓣 → Bangumi 适配 |
| `douban_to_subjectlist` | 豆瓣 JSON | `SubjectUpsertList` | 豆瓣数据导入 |
| `douban_to_collectionlist` | 豆瓣 JSON | `CollectionUpsertList` | 豆瓣收藏导入 |
| `bangumi_calendar_to_schedule_upsert_list` | BangumiCalendar | `ScheduleUpsertList` | 日历 → 排班 |
| `bangumi_calendar_to_subject_upsert_list` | BangumiCalendar | `SubjectUpsertList` | 日历 → 条目 |
| `*_to_unified` 系列 | 各种格式 | `UnifiedList` | 前端统一视图 |

**统一视图模型** (`UnifiedCollectionSubject`)：无论数据源是 Collection 还是 Subject，都转换为相同的格式返回给前端。

### 其他 Schema 文件

| 文件 | 主要 Schema | 用途 |
|------|------------|------|
| `agent.py` | `Message`, `ChatRequest`, `PromptConfig` | Agent 聊天 API |
| `bangumi.py` | `SubjectDetail`, `BangumiCalendar`, `BangumiUserInfo` | Bangumi API 响应 |
| `collection.py` | `CollectionSubject`, `CollectionWithSubject`, `CollectionUpsert` | 收藏 CRUD + 关联查询 |
| `subject.py` | `SubjectRead`, `SubjectSearchByName`, 含 `tags` 和 `meta_tags` | 条目 CRUD + 搜索 |
| `user.py` | `UserCreate`, `UserRead`, `UserUpdate` | 用户管理 |
| `schedule.py` | `ScheduleCreate`, `ScheduleUpsert` | 番剧排班 |
| `dashboard.py` | `DashboardStats` | 仪表盘统计 |

## 依赖关系

**被谁调用**：
- `api/v1/*` — 路由层使用 Schema 做请求体验证和响应类型
- `services/*` — 调用适配器转换外部数据
- `agents/tools.py` — 引用 `SubjectDetail`

**调用谁**：
- `models/enums.py` — `SubjectType`, `CollectionStatus` 枚举
- `schemas/shared.py` — `BaseList`, `SearchBase` 基类
- `schemas/subject.py` — `SubjectRead`, `SubjectUpsert`
- `schemas/collection.py` — `CollectionRead`, `CollectionUpsert`

## 设计模式

- **Upsert 模式**：大量使用 Upsert（即 INSERT OR UPDATE）Schema，适配 Bangumi 数据同步场景
- **统一视图**：`UnifiedCollectionSubject` + 转换函数实现 Collection/Subject/搜索三种数据源的统一前端格式
- **双层嵌套**：`CollectionWithSubject` / `CollectionSubject` 两种关联 Schema，前者 `{collection, subject}` 分拆，后者直接平铺
