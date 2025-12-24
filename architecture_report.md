# OtakuNeko 项目架构巡检报告

## 1. 模块功能索引

| 文件夹     | 主要角色与职责                                             | 核心文件示例                          |
|------------|----------------------------------------------------------|---------------------------------------|
| **core/**  | 项目核心配置与基础组件，提供全局共享的配置和工具函数       | `config.py` (环境变量配置)             |
| **api/**   | API接口层，负责处理HTTP请求和响应，采用版本化路由管理      | `v1/anime.py` (动画数据导入接口)       |
| **models/**| 数据模型层，定义数据库表结构和实体关系                     | `subject.py` (通用条目模型), `anime.py` (动画数据模型，已废弃) |
| **services/** | 业务逻辑层，封装核心业务流程和数据处理逻辑               | `anime_service.py` (动画数据处理服务)  |
| **agents/**| AI智能代理层，用于实现基于数据的AI应用功能                 | `graph.py` (AI工作流定义，待实现)      |

### 详细说明

- **core/**：存放项目的核心配置信息，如数据库连接字符串、API密钥等环境变量配置，是整个项目的基础支撑。
- **api/**：采用RESTful API设计，通过版本化路由（如v1）组织接口，将HTTP请求路由到相应的业务逻辑处理函数。
- **models/**：使用SQLModel定义数据库表结构，同时提供数据验证功能，是数据库操作的基础。
- **services/**：实现核心业务逻辑，如数据的CRUD操作、数据转换、业务规则验证等，是API层和数据层之间的桥梁。
- **agents/**：为AI功能预留的模块，用于实现基于已有数据的智能应用，如推荐系统、数据分析等。

## 2. 数据流向分析

当Bangumi的JSON数据发送到后端时，数据流向如下：

```
客户端 → API路由 (api/v1/anime.py) → 服务层 (services/anime_service.py) → 数据模型 (models/subject.py) → 数据库
```

### 详细流程

1. **API入口**：数据通过`POST /api/v1/anime/ingest`接口进入系统，由`backend/app/api/v1/anime.py`中的`ingest_subject_data`函数接收。

2. **数据验证**：API层首先验证必要字段（id和name）是否存在，如果缺失则返回400错误。

3. **服务层处理**：验证通过后，调用`services/bangumi_service.py`中的`upsert_subject`函数处理数据。

4. **数据解析与转换**：服务层对原始Bangumi数据进行解析，提取并转换为适合数据库存储的格式：
   - 从`images`字段中提取封面图片URL
   - 将`tags`数组转换为仅包含name的列表
   - 从`rating`字段中提取评分信息

5. **数据库操作**：根据Bangumi ID查询数据库，决定执行插入或更新操作，最终将数据持久化到数据库。

6. **响应返回**：操作完成后，将处理结果转换为JSON格式返回给客户端。

## 3. 技术栈联动

SQLModel在本项目中同时充当了"数据库表定义"和"数据验证"的双重角色，其工作原理如下：

### SQLModel的双重角色

| 角色              | 实现方式                                  | 示例代码片段                                          |
|-------------------|-------------------------------------------|-------------------------------------------------------|
| 数据库表定义      | 通过继承SQLModel并设置`table=True`         | `class Anime(SQLModel, table=True):`                  |
| 字段类型映射      | 使用Field定义字段，指定数据库列类型        | `summary: Optional[str] = Field(sa_column=Column(Text))` |
| 数据验证          | 利用Pydantic的类型注解进行数据验证         | `name: str = Field(...)`  # 必填字符串字段            |
| 默认值设置        | 通过Field的default参数设置默认值          | `name_cn: Optional[str] = Field(default="")`         |
| 约束条件          | 使用Field的constraints参数设置约束        | `id: int = Field(primary_key=True)`                   |

### 工作机制

1. **数据库表定义**：
   - SQLModel继承了SQLAlchemy的功能，可以通过`SQLModel.metadata.create_all()`创建数据库表
   - 支持复杂的关系定义（如外键、一对一、一对多关系）
   - 可以使用SQLAlchemy的高级特性（如索引、视图等）

2. **数据验证**：
   - 继承了Pydantic的数据验证功能，自动验证输入数据的类型和约束
   - 支持自定义验证逻辑
   - 在API层面和数据库层面都能提供数据验证

3. **自动API文档**：
   - FastAPI可以自动生成API文档，包括请求参数和响应模型
   - 支持Swagger UI和ReDoc接口文档

## 4. API 职责分离与更新策略

### 4.1 API 职责分离

为了提高系统的可维护性和安全性，项目采用了 API 职责分离的设计：

| API 路径 | 职责 | 数据类型 | 认证要求 |
|---------|------|---------|---------|
| `/api/v1/subjects/` | 条目库查询 | 公有数据 | 可选 |
| `/api/v1/collections/` | 我的收藏查询与更新 | 私有数据 | 必须 |

- **`/subjects/`**：负责处理公有条目数据的查询，任何人都可以访问，无需认证。
- **`/collections/`**：负责处理用户私有收藏数据的查询和更新，必须进行用户认证。

这种设计使得 API 接口更加清晰，便于维护和扩展，同时也提高了系统的安全性，保护了用户的私有数据。

### 4.2 PATCH 更新策略

对于收藏信息的更新，项目采用了 HTTP PATCH 方法，支持局部更新：

- **请求方法**：PATCH `/api/v1/collections/{subject_id}`
- **请求体**：仅包含需要更新的字段
- **响应**：返回更新后的完整收藏信息

#### 实现机制

```python
# backend/app/services/collection_service.py
async def update_collection(
    db: AsyncSession, user_id: int, subject_id: int, update_data: CollectionUpdate
) -> Optional[Collection]:
    # 查询收藏记录
    query = select(Collection).where(
        Collection.user_id == user_id,
        Collection.subject_id == subject_id
    )
    collection = (await db.execute(query)).scalar_one_or_none()
    
    if not collection:
        return None
    
    # 仅更新非空字段
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(collection, field, value)
    
    # 更新时间戳
    collection.updated_at = datetime.now()
    
    # 保存更新
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    
    return collection
```

这种策略的优势：
1. **减少网络传输**：只需要发送需要更新的字段，减少了数据传输量
2. **提高性能**：减少了数据库操作的复杂度
3. **灵活性**：允许客户端只更新感兴趣的字段
4. **清晰的语义**：使用 PATCH 方法明确表示是局部更新操作

## 5. 关键配置说明

`.env`、`docker-compose.yml` 和 `backend/app/core/db.py` 之间通过环境变量实现了无缝配合，确保后端能够成功连接到数据库。

### 配置文件协同工作流程

1. **docker-compose.yml**：
   - 定义了PostgreSQL和Redis服务的容器配置
   - 设置了数据库的用户名、密码、端口等基础配置
   - 通过卷挂载实现数据持久化

2. **.env**：
   - 定义了数据库连接字符串（`DATABASE_URL`）
   - 配置了数据库的主机、端口、用户名、密码等信息
   - 与docker-compose.yml中的数据库配置保持一致

3. **backend/app/core/db.py**：
   - 从配置文件中加载数据库连接字符串
   - 创建异步数据库引擎和会话工厂
   - 提供数据库初始化和会话获取功能

### 配置流程示意图

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ docker-compose.yml │→→→│       .env      │→→→│ backend/app/core/db.py │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                         │                        │
        ▼                         ▼                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ PostgreSQL 容器 │     │ 环境变量配置    │     │ 数据库连接引擎   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## 5. AI 准备就绪度

基于当前的项目结构，`agents/` 文件夹可以通过以下方式调用 `models/` 里的数据：

### 数据访问方式

1. **直接数据库访问**：
   - 使用 `db.py` 中提供的 `get_session()` 函数获取数据库会话
   - 通过 SQLModel 的查询接口访问 `models/` 中的数据
   - 示例代码：
     ```python
     from sqlmodel import select
     from sqlalchemy.ext.asyncio import AsyncSession
     from app.models.subject import Subject
     from app.db.database import get_session

     async def get_subject_recommendations(): 
         async for session in get_session():  # 获取数据库会话
             result = await session.execute(select(Subject).order_by(Subject.score.desc()))
             top_subjects = result.scalars().all()
             return [subject.name for subject in top_subjects[:10]]
     ```

2. **服务层调用**：
   - 调用 `services/` 中已实现的业务逻辑函数
   - 避免直接操作数据库，提高代码复用性

### AI 功能实现建议

1. **推荐系统**：基于用户历史数据和动画标签，实现个性化推荐
2. **数据分析**：对动画数据进行统计分析，生成趋势报告
3. **内容生成**：利用AI生成动画简介、标签等内容
4. **问答系统**：基于动画数据实现智能问答功能

### 工作流设计

`agents/graph.py` 可以使用LangGraph等工具构建AI工作流，实现复杂的AI功能：

```
数据输入 → 数据处理 → AI模型调用 → 结果生成 → 数据输出
```

## 6. 数据同步模块

### 概述

数据同步模块实现了从Bangumi API获取用户收藏数据并同步到本地数据库的功能，支持完整的异步数据处理流程。该模块经过重构，现已支持Bangumi的**全品类**（书籍/动画/音乐/游戏/三次元）收藏同步。

### 全品类支持实现

为了支持Bangumi的全品类收藏，系统进行了以下核心设计：

#### 6.1 枚举类型定义

创建了两个关键枚举类型用于规范数据格式：

```python
# backend/app/models/enums.py
from enum import IntEnum

class SubjectType(IntEnum):
    """Bangumi条目类型枚举"""
    BOOK = 1  # 书籍/小说
    ANIME = 2  # 动画
    MUSIC = 3  # 音乐
    GAME = 4  # 游戏
    REAL = 6  # 三次元

class CollectionStatus(IntEnum):
    """Bangumi收藏状态枚举"""
    WISH = 1  # 想看
    COLLECT = 2  # 看过
    DO = 3  # 在看
    ON_HOLD = 4  # 搁置
    DROPPED = 5  # 抛弃
```

#### 6.2 Subject模型设计

使用通用的`Subject`模型替代了原有的`Anime`模型，支持存储全品类数据：

```python
# backend/app/models/subject.py
class Subject(SQLModel, table=True):  # type: ignore[call-arg]
    """通用条目模型，支持全品类数据存储"""
    # 基础信息
    id: int = Field(primary_key=True, description="Bangumi条目ID")
    type: SubjectType = Field(description="条目类型：1=书籍, 2=动画, 3=音乐, 4=游戏, 6=三次元")
    name: str = Field(description="条目原名")
    name_cn: Optional[str] = Field(default="", description="条目中文名")
    summary: Optional[str] = Field(sa_column=Column(Text), description="条目简介")
    cover_url: str = Field(default="", description="封面URL")
    date: Optional[str] = Field(default="", description="发售/放送日期")
    platform: Optional[str] = Field(default="", description="平台")
    
    # 数值/统计信息
    score: Optional[float] = Field(default=None, description="评分")
    rank: Optional[int] = Field(default=None, description="排名")
    eps: Optional[int] = Field(default=None, description="集数")
    volumes: Optional[int] = Field(default=None, description="卷数")
    collection_total: Optional[int] = Field(default=None, description="总收藏人数")
    
    # 复杂结构（JSON存储）
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON), description="标签列表")
    meta_tags: List[str] = Field(default_factory=list, sa_column=Column(JSON), description="官方元标签")
    infobox: List[Dict[str, str]] = Field(default_factory=list, sa_column=Column(JSON), description="元数据")
    rating_details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON), description="评分分布详情")
    
    # 与Collection模型关系
    collections: List[Collection] = Relationship(back_populates="subject")
```

#### 6.3 Collection模型更新

Collection模型已更新为与Subject模型关联，并使用枚举类型规范收藏状态：

```python
# backend/app/models/collection.py
class Collection(SQLModel, table=True):  # type: ignore[call-arg]
    """用户收藏模型，支持全品类条目收藏"""
    subject_id: int = Field(primary_key=True, foreign_key="subject.id", description="关联的条目ID")
    type: CollectionStatus = Field(description="收藏状态：1想看/2看过/3在看/4搁置/5抛弃")
    rate: Optional[int] = Field(default=None, description="用户评分")
    updated_at: datetime = Field(description="最后更新时间")
    private: bool = Field(default=False, description="是否私密收藏")
    
    # 与Subject模型建立关系
    subject: "Subject" = Relationship(back_populates="collections")
```

### 6.4 智能数据清洗逻辑

为了处理Bangumi API两种不同的数据格式（Type A: 嵌套Subject对象和Type B: 完整详情），实现了智能的数据清洗函数`upsert_subject`：

```python
# backend/app/services/bangumi_service.py
async def upsert_subject(db: AsyncSession, subject_data: Dict[str, Any]) -> Subject:
    """智能映射并清洗Subject数据，支持Type A (Nested) 和 Type B (Full) 两种格式"""
    # 处理Type A (嵌套在收藏数据中的Subject)
    if "subject" in subject_data:
        subject_data = subject_data["subject"]
    
    # 处理summary和short_summary：优先使用summary，如果没有且数据库中也没有，则使用short_summary
    summary = subject_data.get("summary")
    short_summary = subject_data.get("short_summary")
    # ... 智能处理逻辑
    
    # 处理封面图片
    cover_url = ""
    images = subject_data.get("images", {})
    if images:
        cover_url = images.get("large", images.get("common", ""))
    
    # 处理评分信息 (Type A扁平格式 vs Type B嵌套格式)
    score = None
    rank = None
    rating_details = {}
    
    if "rating" in subject_data:
        # Type B格式
        rating = subject_data["rating"]
        score = rating.get("score")
        rank = rating.get("rank")
        rating_details = rating.copy()
    else:
        # Type A格式
        score = subject_data.get("score")
        rank = subject_data.get("rank")
        # ... 其他处理逻辑
    
    # 处理集数/卷数
    eps = subject_data.get("eps")
    total_episodes = subject_data.get("total_episodes")
    # 如果有total_episodes则优先使用，否则使用eps
    final_eps = total_episodes if total_episodes is not None else eps
    
    # ... 创建或更新Subject对象
```

#### 关键数据处理策略

| 字段冲突 | 处理策略 |
|---------|---------|
| `summary` vs `short_summary` | 优先使用完整的`summary`，如果没有且数据库中也没有，则使用`short_summary` |
| `rating.score` vs `score` | 支持Type A扁平格式和Type B嵌套格式的评分数据 |
| `eps` vs `total_episodes` | 优先使用`total_episodes`，如果没有则使用`eps` |
| `images.large` vs `images.common` | 优先使用高质量的`large`尺寸图片，否则使用`common`尺寸 |

### 同步流程

完整的数据同步流程如下：

```
外部Bangumi API → 数据清洗与转换 → Subject表入库 → Collection表入库
```

**详细步骤**：

1. **外部API调用**：通过`bangumi_client.py`中的`fetch_user_collections`函数，支持按类型获取不同品类的收藏数据
   - API地址：`https://api.bgm.tv/v0/users/{username}/collections`
   - 支持参数：`subject_type` (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
   - 设置合规的User-Agent头信息

2. **数据清洗与转换**：
   - 使用`upsert_subject`函数智能处理Type A和Type B两种数据格式
   - 确保数据的一致性和完整性

3. **Subject表入库**：将清洗后的数据保存到Subject表，支持批量操作

4. **Collection表入库**：将收藏元数据保存到Collection表，建立与Subject表的关联

### API接口更新

更新后的API接口支持全品类收藏同步：

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/anime/ingest` | 接收Bangumi的原始JSON数据并保存到数据库，支持全品类条目 |
| GET | `/api/v1/anime/sync/{username}` | 同步指定用户的收藏数据到本地数据库，支持按类型筛选 |
| GET | `/api/v1/anime/subject/{subject_id}/sync` | 同步单个条目的详细信息 |

**请求示例**：
```
# 同步用户所有收藏
GET /api/v1/anime/sync/myusername

# 仅同步用户的书籍收藏
GET /api/v1/anime/sync/myusername?subject_type=1

# 同步单个条目详情
GET /api/v1/anime/subject/300270/sync
```

**响应示例**：
```json
{
  "message": "Successfully synced 42 collections for user myusername",
  "username": "myusername",
  "sync_count": 42,
  "subject_type": 1
}
```

### 事务处理

数据同步过程中使用了事务处理确保数据一致性：

- 使用`async with db.begin_nested()`为每个收藏项创建嵌套事务
- 确保动画基础信息和收藏信息要么同时成功入库，要么同时失败
- 单个收藏项的处理失败不会影响整体同步流程

### 异常处理

实现了完整的异常处理机制：
- HTTP状态错误处理（如404用户不存在）
- 网络超时和连接错误处理
- 数据解析错误处理

## 总结

OtakuNeko项目采用了清晰的分层架构设计，各模块职责明确，数据流向清晰，为后续功能扩展和AI集成提供了良好的基础。项目使用了现代化的技术栈，如FastAPI、SQLModel、异步数据库操作等，确保了系统的高性能和可维护性。

新实现的数据同步模块进一步增强了系统功能，支持从外部API获取用户收藏数据并同步到本地数据库，为后续的数据分析和AI应用提供了更丰富的数据来源。

当前架构已经为AI功能做好了准备，`agents/` 文件夹可以通过多种方式访问和利用 `models/` 中的数据，实现丰富的智能应用功能。