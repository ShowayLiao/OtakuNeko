# OtakuNeko 后端技术文档

## 目录

- [1. 应用程序架构概述](#1-应用程序架构概述)
- [2. 模块功能与职责](#2-模块功能与职责)
- [3. API端点文档](#3-api端点文档)
- [4. 数据库模型与模式定义](#4-数据库模型与模式定义)
- [5. 服务层实现细节](#5-服务层实现细节)
- [6. 配置管理](#6-配置管理)
- [7. 缓存机制](#7-缓存机制)
- [8. 认证系统](#8-认证系统)
- [9. Repository 模式](#9-repository-模式)
- [10. 开发规范](#10-开发规范)
- [11. 部署流程](#11-部署流程)

---

## 1. 应用程序架构概述

### 1.1 技术栈

| 组件 | 技术选型 | 版本 | 用途 |
|------|---------|------|------|
| Web框架 | FastAPI | Latest | 高性能异步 Web 框架 |
| ASGI服务器 | Uvicorn | Latest | ASGI 服务器实现 |
| ORM | SQLModel | Latest | 基于 Pydantic 的 ORM |
| 数据库驱动 | asyncpg | Latest | PostgreSQL 异步驱动 |
| 缓存 | Redis | Latest | 高性能缓存数据库 |
| 配置管理 | pydantic-settings | Latest | 环境变量配置管理 |
| HTTP客户端 | httpx | Latest | 异步 HTTP 客户端 |
| 认证 | JWT (python-jose) | Latest | JSON Web Token 认证 |
| 密码加密 | passlib | Latest | 密码哈希处理 |
| 缓存框架 | fastapi-cache2 | Latest | FastAPI 缓存装饰器 |
| AI/Agent | LangGraph, LangChain | Latest | AI 智能体框架 |

### 1.2 架构设计

OtakuNeko后端采用**分层架构**设计，遵循关注点分离原则：

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (路由层)                    │
│  - app/api/v1/auth.py (认证接口)                         │
│  - app/api/v1/subjects.py (条目接口)                     │
│  - app/api/v1/collections.py (收藏接口)                  │
│  - app/api/v1/users.py (用户接口)                        │
│  - app/api/v1/dashboard.py (仪表盘接口)                  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              Dependency Layer (依赖层)                   │
│  - app/api/deps.py (认证依赖注入)                        │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Service Layer (服务层)                 │
│  - app/services/bangumi_service.py                      │
│  - app/services/collection_service.py                   │
│  - app/services/subject_service.py                      │
│  - app/services/stats_service.py                        │
│  - app/services/bangumi_client.py                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              Repository Layer (数据访问层)              │
│  - app/repositories/subject_repo.py                     │
│  - app/repositories/collection_repo.py                  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Model Layer (模型层)                   │
│  - app/models/subject.py                                │
│  - app/models/collection.py                             │
│  - app/models/user.py                                   │
│  - app/models/enums.py                                  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                 Database Layer (数据层)                 │
│  - PostgreSQL (主数据库)                                 │
│  - Redis (缓存)                                         │
└─────────────────────────────────────────────────────────┘
```

### 1.3 核心设计模式

1. **Repository模式**: 通过 Repository 层封装数据访问逻辑，实现业务逻辑与数据访问的分离
2. **适配器模式**: 将 Bangumi/豆瓣数据适配为统一格式
3. **依赖注入**: 使用 FastAPI 的 Depends 机制实现依赖注入
4. **缓存装饰器**: 使用 fastapi-cache2 实现声明式缓存
5. **异步编程**: 全面使用 async/await 提升性能
6. **JWT 认证**: 基于令牌的无状态认证机制

### 1.4 数据流程

#### 1.4.1 用户认证流程

```
┌─────────┐
│  前端   │
└────┬────┘
     │ POST /api/v1/auth/login
     │ {"username": "user"}
     ▼
┌─────────────────┐
│  Auth API       │
│  - 查询用户     │
│  - 不存在则创建 │
│  - 生成 JWT     │
└────┬────────────┘
     │ 返回 token
     ▼
┌─────────┐
│  前端   │ (存储 token)
└────┬────┘
     │ 请求携带 Authorization: Bearer <token>
     ▼
┌─────────────────┐
│  get_current_user│
│  - 解码 JWT     │
│  - 查询用户     │
│  - 返回 User    │
└─────────────────┘
```

#### 1.4.2 数据同步流程

```
┌─────────┐
│  前端   │
└────┬────┘
     │ POST /api/v1/collections/sync
     ▼
┌─────────────────┐
│  Collection API │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│  Service Layer  │
│  - 调用 SubjectRepo.save()
│  - 调用 CollectionRepo.save()
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│ Repository Layer│
│  - 查询/创建 Subject
│  - 查询/创建 Collection
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│   Database      │
└─────────────────┘
```

#### 1.4.3 缓存流程

```
┌─────────┐
│  请求    │
└────┬────┘
     │
     ▼
┌─────────────────┐
│  Cache Decorator│
│  - 检查缓存    │
│  - 命中则返回   │
└────┬────────────┘
     │ 未命中
     ▼
┌─────────────────┐
│  执行函数       │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│  写入缓存       │
└────┬────────────┘
     │
     ▼
┌─────────┐
│  返回    │
└─────────┘
```

---

## 2. 模块功能与职责

### 2.1 目录结构

```
backend/app/
├── __init__.py              # 应用初始化
├── main.py                  # FastAPI应用入口
├── agents/                  # AI Agent模块 (待实现)
│   ├── __init__.py
│   ├── graph.py
│   └── nodes/
│       ├── __init__.py
│       └── basic_node.py
├── api/                     # API路由层
│   ├── __init__.py
│   ├── deps.py              # 依赖注入 (认证)
│   └── v1/
│       ├── __init__.py
│       ├── auth.py          # 认证接口
│       ├── agent.py         # Agent相关API (待实现)
│       ├── collections.py   # 收藏接口
│       ├── dashboard.py     # 仪表盘接口
│       ├── subjects.py      # 条目接口
│       └── users.py         # 用户接口
├── core/                    # 核心配置
│   ├── __init__.py
│   ├── config.py            # 配置管理
│   └── security.py          # 安全工具 (JWT, 密码)
├── db/                      # 数据库连接
│   ├── __init__.py
│   └── database.py          # 数据库初始化
├── models/                  # 数据模型
│   ├── __init__.py
│   ├── collection.py        # 收藏模型
│   ├── enums.py             # 枚举类型
│   ├── subject.py           # 条目模型
│   └── user.py              # 用户模型
├── repositories/            # 数据访问层
│   ├── __init__.py
│   ├── collection_repo.py   # 收藏数据访问
│   └── subject_repo.py      # 条目数据访问
├── schemas/                 # Pydantic Schema
│   ├── __init__.py
│   ├── adapters.py          # 数据适配器
│   ├── collection.py        # 收藏 Schema
│   ├── common.py            # 通用 Schema
│   ├── dashboard.py         # 仪表盘 Schema
│   ├── subject.py           # 条目 Schema
│   └── user.py              # 用户 Schema
├── services/                # 业务逻辑层
│   ├── __init__.py
│   ├── bangumi_client.py    # Bangumi API 客户端
│   ├── bangumi_service.py   # Bangumi 业务逻辑
│   ├── collection_service.py# 收藏业务逻辑
│   ├── douban_importer.py   # 豆瓣数据导入
│   ├── stats_service.py     # 统计服务
│   └── subject_service.py   # 条目搜索服务
├── utils/                   # 工具函数 (空目录)
└── worker/                  # 异步任务 (待实现)
    ├── __init__.py
    └── celery_app.py
```

### 2.2 模块职责说明

| 模块 | 职责 | 状态 |
|------|------|------|
| [main.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/main.py) | 应用入口、生命周期管理、中间件配置、缓存初始化 | ✅ 已实现 |
| [api/v1/auth.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/auth.py) | 用户登录/注册、JWT 令牌签发 | ✅ 已实现 |
| [api/deps.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/deps.py) | 认证依赖注入、当前用户获取 | ✅ 已实现 |
| [api/v1/subjects.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/subjects.py) | 条目搜索、详情获取、同步 | ✅ 已实现 |
| [api/v1/collections.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/collections.py) | 收藏管理、导入导出 | ✅ 已实现 |
| [api/v1/users.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/users.py) | 用户注册、信息查询 | ✅ 已实现 |
| [api/v1/dashboard.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/dashboard.py) | 仪表盘统计 | ✅ 已实现 |
| [core/security.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/core/security.py) | JWT 令牌创建/解码、密码哈希/验证 | ✅ 已实现 |
| [core/config.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/core/config.py) | 环境配置管理 | ✅ 已实现 |
| [repositories/subject_repo.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/repositories/subject_repo.py) | Subject 数据访问层 | ✅ 已实现 |
| [repositories/collection_repo.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/repositories/collection_repo.py) | Collection 数据访问层 | ✅ 已实现 |
| [models/subject.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/models/subject.py) | 条目数据模型 | ✅ 已实现 |
| [models/collection.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/models/collection.py) | 收藏数据模型 | ✅ 已实现 |
| [models/user.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/models/user.py) | 用户数据模型 | ✅ 已实现 |
| [services/bangumi_service.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/bangumi_service.py) | Bangumi 数据处理 | ✅ 已实现 |
| [services/collection_service.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/collection_service.py) | 收藏业务逻辑 | ✅ 已实现 |
| [services/subject_service.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/subject_service.py) | 条目搜索服务 | ✅ 已实现 |
| [services/stats_service.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/stats_service.py) | 统计数据服务 | ✅ 已实现 |
| [services/douban_importer.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/douban_importer.py) | 豆瓣数据导入 | ✅ 已实现 |
| [agents/](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/) | AI Agent 功能 | 🚧 待实现 |
| [worker/](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/worker/) | 异步任务处理 | 🚧 待实现 |

---

## 3. API端点文档

### 3.1 基础信息

- **Base URL**: `http://localhost:8000`
- **API Version**: `v1`
- **认证方式**: JWT Bearer Token
- **认证头**: `Authorization: Bearer <token>`

### 3.2 认证相关 API

#### POST `/api/v1/auth/login`
用户登录/注册接口

采用"存在即登录"策略：
- 如果用户名已存在，直接返回该用户的 JWT token
- 如果用户名不存在，自动创建新用户并返回 JWT token

**请求体**:
```json
{
  "username": "testuser"
}
```

**请求参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 (1-50字符) |

**响应示例**:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**错误响应**:
```json
{
  "detail": "登录失败: 详细错误信息"
}
```

---

### 3.3 健康检查

#### GET `/`
获取应用欢迎信息

**响应示例**:
```json
{
  "message": "OtakuNeko V2 Backend is running!"
}
```

#### GET `/health`
健康检查端点

**响应示例**:
```json
{
  "status": "ok"
}
```

---

### 3.4 条目相关 API

#### GET `/api/v1/subjects/`
统一搜索接口，支持本地、远程和混合搜索

**请求参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 否 | 搜索关键词 |
| source | string | 否 | 搜索来源: local=仅本地, remote=仅远程, mixed=混合(默认) |
| type | int | 否 | 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) |
| limit | int | 否 | 返回结果数量 (1-100, 默认20) |
| offset | int | 否 | 结果偏移量 (默认0) |
| sort | string | 否 | 排序方式 (rank/score/date, 仅remote模式有效) |

**认证**: 需要 JWT Token

**响应示例**:
```json
[
  {
    "id": 12345,
    "name": "EVA",
    "name_cn": "新世纪福音战士",
    "cover_url": "https://...",
    "type": 2,
    "score": 8.9,
    "rank": 1
  }
]
```

---

#### GET `/api/v1/subjects/{subject_id}`
获取单个条目详情

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| subject_id | int | 条目ID |

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| refresh | bool | 是否从远程刷新数据 (默认false) |

**认证**: 需要 JWT Token

**响应**: SubjectRead 对象

---

#### POST `/api/v1/subjects/ingest`
接收 Bangumi 原始 JSON 数据并保存到数据库

**请求体**: Bangumi API 返回的原始 JSON 数据

**认证**: 需要 JWT Token

**响应示例**:
```json
{
  "message": "Subject data saved successfully",
  "data": { ... }
}
```

---

### 3.5 收藏相关 API

#### GET `/api/v1/collections/`
获取用户收藏列表

**请求参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| subject_type | int | 否 | 条目类型 |
| status | string | 否 | 收藏状态 (watching/completed/plan/on_hold/dropped) |
| keyword | string | 否 | 搜索关键词 |
| limit | int | 否 | 分页大小 (默认20) |
| offset | int | 否 | 分页偏移 (默认0) |
| sort_by | string | 否 | 排序字段 (updated_at/rate/score/rank/date) |

**认证**: 需要 JWT Token

**响应示例**:
```json
{
  "total": 100,
  "items": [
    {
      "subject_id": 12345,
      "updated_at": "2024-01-01T00:00:00",
      "status": 3,
      "rate": 9,
      "comment": "神作",
      "private": false,
      "tags": ["科幻", "机甲"],
      "subject": {
        "id": 12345,
        "name": "EVA",
        "name_cn": "新世纪福音战士",
        "cover_url": "https://...",
        "type": 2,
        "score": 8.9,
        "rank": 1
      }
    }
  ]
}
```

---

#### GET `/api/v1/collections/{subject_id}`
获取当前用户对特定条目的收藏状态

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| subject_id | int | 条目ID |

**认证**: 需要 JWT Token

**响应**: CollectionOut 对象

---

#### PATCH `/api/v1/collections/{subject_id}`
更新用户的收藏信息

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| subject_id | int | 条目ID |

**请求体**:
```json
{
  "status": 3,
  "rate": 9,
  "comment": "神作",
  "private": false,
  "tags": ["科幻", "机甲"]
}
```

**认证**: 需要 JWT Token

**响应**: 更新后的 Collection 对象

---

#### POST `/api/v1/collections/sync`
同步用户的 Bangumi 收藏数据到本地数据库

**请求参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| subject_type | int | 否 | 条目类型 |

**认证**: 需要 JWT Token

**响应示例**:
```json
{
  "message": "Successfully synced 50 collections",
  "sync_count": 50,
  "subject_type": 2
}
```

---

#### POST `/api/v1/collections/sync/douban`
从上传的 JSON 文件导入豆瓣收藏数据

**请求参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 豆瓣 JSON 文件 |
| subject_type | int | 否 | 条目类型覆盖参数 |

**认证**: 需要 JWT Token

**响应示例**:
```json
{
  "message": "Successfully imported 100 Douban items",
  "import_count": 100
}
```

---

#### POST `/api/v1/collections/manual`
手动添加收藏

**请求体**:
```json
{
  "name": "条目标题",
  "type": 2,
  "status": 3,
  "cover_url": "https://...",
  "rate": 9,
  "comment": "评论",
  "release_date": "2024-01-01",
  "publish_date": "2024-01-15",
  "tags": "标签1,标签2"
}
```

**认证**: 需要 JWT Token

---

### 3.6 用户相关 API

#### GET `/api/v1/users/info`
获取当前用户信息

**认证**: 需要 JWT Token

**响应示例**:
```json
{
  "id": 1,
  "username": "testuser",
  "email": null,
  "avatar_url": "https://...",
  "bangumi_id": null,
  "sign": "本地用户",
  "created_at": "2024-01-01T00:00:00"
}
```

---

### 3.7 仪表盘相关 API

#### GET `/api/v1/dashboard/stats`
获取仪表盘统计数据

**认证**: 需要 JWT Token

**响应示例**:
```json
{
  "anime": 50,
  "book": 30,
  "music": 20,
  "game": 10,
  "real": 5
}
```

**缓存**: 10分钟

---

## 4. 数据库模型与模式定义

### 4.1 数据库表关系图

```
┌─────────────┐
│    User     │
├─────────────┤
│ id (PK)     │
│ username    │
│ nickname    │
│ email       │
│ avatar_url  │
│ bangumi_id  │
│ sign        │
│ created_at  │
│ updated_at  │
└──────┬──────┘
       │ 1
       │
       │ N
┌──────▼──────────────────┐
│     Collection          │
├─────────────────────────┤
│ user_id (PK, FK)        │
│ subject_id (PK, FK)     │
│ type (收藏状态)          │
│ rate (评分)              │
│ comment (评论)           │
│ updated_at               │
│ private (是否私密)       │
│ tags (JSON标签)          │
└──────┬──────────────────┘
       │ N
       │
       │ 1
┌──────▼──────────────────┐
│      Subject            │
├─────────────────────────┤
│ id (PK)                 │
│ source (数据源)          │
│ source_id (原站ID)      │
│ type (条目类型)          │
│ name (原名)              │
│ name_cn (中文名)         │
│ summary (简介)           │
│ cover_url (封面)         │
│ date (日期)              │
│ platform (平台)          │
│ score (评分)             │
│ rank (排名)              │
│ eps (集数)               │
│ volumes (卷数)           │
│ collection_total         │
│ tags (JSON标签)          │
│ meta_tags (JSON)         │
│ infobox (JSON)           │
│ rating_details (JSON)    │
│ images (JSON)            │
└─────────────────────────┘
```

### 4.2 User 模型

**文件**: [models/user.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/models/user.py)

```python
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    nickname: str
    email: str = Field(unique=True, nullable=True)
    avatar_url: Optional[str] = Field(default=None)
    bangumi_id: Optional[int] = Field(default=None, index=True)
    sign: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

**字段说明**:
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, 自增 | 用户ID |
| username | string | UNIQUE, INDEX | 用户名 |
| nickname | string | - | 昵称 |
| email | string | UNIQUE, NULLABLE | 邮箱 |
| avatar_url | string | NULLABLE | 头像URL |
| bangumi_id | int | INDEX, NULLABLE | Bangumi ID |
| sign | string | NULLABLE | 个性签名 |
| created_at | datetime | - | 创建时间 |
| updated_at | datetime | - | 更新时间 |

---

### 4.3 Subject 模型

**文件**: [models/subject.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/models/subject.py)

```python
class Subject(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(default="bangumi", index=True)
    source_id: str = Field(index=True)
    type: SubjectType = Field(index=True)
    name: str
    name_cn: Optional[str] = Field(default="")
    summary: Optional[str] = Field(sa_column=Column(Text))
    cover_url: str = Field(default="")
    date: Optional[str] = Field(default="")
    platform: Optional[str] = Field(default="")
    score: Optional[float] = Field(default=None)
    rank: Optional[int] = Field(default=None)
    eps: Optional[int] = Field(default=None)
    volumes: Optional[int] = Field(default=None)
    collection_total: Optional[int] = Field(default=None)
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    meta_tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    infobox: List[Dict[str, str]] = Field(default_factory=list, sa_column=Column(JSON))
    rating_details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    images: Dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
```

**字段说明**:
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, 自增 | 条目ID |
| source | string | INDEX | 数据源 (bangumi/douban) |
| source_id | string | INDEX | 原站ID |
| type | SubjectType | INDEX | 条目类型枚举 |
| name | string | - | 原名 |
| name_cn | string | - | 中文名 |
| summary | string | TEXT | 简介 |
| cover_url | string | - | 封面URL |
| date | string | - | 日期 |
| platform | string | - | 平台 |
| score | float | - | 评分 |
| rank | int | - | 排名 |
| eps | int | - | 集数 |
| volumes | int | - | 卷数 |
| collection_total | int | - | 收藏总数 |
| tags | JSON | - | 标签列表 |
| meta_tags | JSON | - | 元标签 |
| infobox | JSON | - | 信息框 |
| rating_details | JSON | - | 评分详情 |
| images | JSON | - | 图片信息 |

---

### 4.4 Collection 模型

**文件**: [models/collection.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/models/collection.py)

```python
class Collection(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    subject_id: int = Field(foreign_key="subject.id", primary_key=True)
    type: Optional[CollectionStatus] = Field(default=None)
    rate: Optional[int] = Field(default=None)
    comment: Optional[str] = Field(sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=datetime.now)
    private: bool = Field(default=False)
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
```

**字段说明**:
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| user_id | int | PK, FK | 用户ID |
| subject_id | int | PK, FK | 条目ID |
| type | CollectionStatus | - | 收藏状态枚举 |
| rate | int | - | 评分 (1-10) |
| comment | string | TEXT | 评论 |
| updated_at | datetime | - | 更新时间 |
| private | bool | - | 是否私密 |
| tags | JSON | - | 标签列表 |

---

## 5. 服务层实现细节

### 5.1 Bangumi Service

**文件**: [services/bangumi_service.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/bangumi_service.py)

**主要功能**:
- 同步用户收藏数据
- 同步单个条目详情
- 使用 Repository 模式进行数据访问

**关键方法**:
```python
async def sync_user_collections(username: str, db: AsyncSession, subject_type: Optional[int] = None) -> int
async def sync_subject_detail(bgm_id: int, db: AsyncSession) -> Subject
```

---

### 5.2 Stats Service

**文件**: [services/stats_service.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/services/stats_service.py)

**主要功能**:
- 获取用户收藏统计数据
- 使用缓存优化性能

**关键方法**:
```python
@cache(expire=600, namespace="dashboard", key_builder=stats_key_builder)
async def get_user_stats(user_id: int, db: AsyncSession) -> DashboardStats
```

---

## 6. 配置管理

### 6.1 配置文件

**文件**: [core/config.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/core/config.py)

```python
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "OtakuNeko"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    
    DATABASE_URL: str = "postgresql+asyncpg://otaku:password@localhost:5432/otakuneko"
    REDIS_URL: str = "redis://localhost:6379/0"
    OPENAI_API_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

### 6.2 环境变量

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| DATABASE_URL | string | - | PostgreSQL 连接字符串 |
| REDIS_URL | string | redis://localhost:6379/0 | Redis 连接字符串 |
| OPENAI_API_KEY | string | - | OpenAI API 密钥 (可选) |
| DEBUG | bool | True | 调试模式 |

---

## 7. 缓存机制

### 7.1 缓存架构

OtakuNeko 使用 Redis 作为缓存后端，通过 fastapi-cache2 实现声明式缓存。

**初始化** (在 [main.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/main.py)):
```python
from fastapi_cache import FastAPICache
from fastapi_cache.coder import PickleCoder
from fastapi_cache.backends.redis import RedisBackend
from redis.asyncio import Redis

redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
FastAPICache.init(
    RedisBackend(redis),
    expire=60,
    prefix="fastapi-cache-v2",
    coder=PickleCoder
)
```

### 7.2 缓存策略

| 接口 | 缓存时间 | 说明 |
|------|---------|------|
| GET /api/v1/subjects/ | 60秒 | 条目搜索 |
| GET /api/v1/subjects/{id} | 7天 | 条目详情 |
| GET /api/v1/dashboard/stats | 10分钟 | 用户统计 |

### 7.3 自定义缓存 Key

为用户相关数据生成独立的缓存 key：

```python
def stats_key_builder(func, namespace: str, request, *args, **kwargs):
    user_id = kwargs.get("user_id", args[0] if args else None)
    return f"dashboard:stats:{user_id}"
```

### 7.4 缓存使用示例

```python
from fastapi_cache.decorator import cache

@cache(expire=600, namespace="dashboard", key_builder=stats_key_builder)
async def get_user_stats(user_id: int, db: AsyncSession) -> DashboardStats:
    pass
```

---

## 8. 认证系统

### 8.1 认证架构

OtakuNeko 使用 JWT (JSON Web Token) 实现无状态认证。

**认证流程**:
1. 用户提交用户名
2. 系统查询或创建用户
3. 系统生成 JWT token
4. 客户端存储 token
5. 后续请求携带 token
6. 系统验证 token 并获取用户信息

### 8.2 JWT 配置

**文件**: [core/security.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/core/security.py)

```python
from datetime import datetime, timedelta
from jose import JWTError, jwt

SECRET_KEY = settings.OPENAI_API_KEY or "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天
```

### 8.3 JWT 工具函数

#### 创建访问令牌

```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, str(SECRET_KEY), algorithm=ALGORITHM)
```

#### 解码访问令牌

```python
def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, str(SECRET_KEY), algorithms=[ALGORITHM])
    except JWTError:
        return None
```

### 8.4 认证依赖

**文件**: [api/deps.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/deps.py)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_session)
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="无法验证凭据")
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="无法验证凭据")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    return user
```

### 8.5 登录接口

**文件**: [api/v1/auth.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/auth.py)

```python
@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalars().first()
    
    if user:
        token = create_access_token(data={"sub": str(user.id), "username": user.username})
        return LoginResponse(token=token)
    else:
        new_user = User(
            username=data.username,
            nickname=data.username,
            sign="本地用户"
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        token = create_access_token(data={"sub": str(new_user.id), "username": new_user.username})
        return LoginResponse(token=token)
```

### 8.6 使用认证

在需要认证的接口中使用 `get_current_user` 依赖：

```python
@router.get("/collections/")
async def get_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    pass
```

---

## 9. Repository 模式

### 9.1 设计理念

Repository 模式将数据访问逻辑从业务逻辑层分离，提供以下优势：
- 关注点分离：业务逻辑与数据访问解耦
- 可测试性：便于 Mock 数据访问层
- 可维护性：统一的数据访问接口
- 可扩展性：易于切换数据源

### 9.2 Subject Repository

**文件**: [repositories/subject_repo.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/repositories/subject_repo.py)

```python
class SubjectRepo:
    @staticmethod
    async def save(db: AsyncSession, subject_data: Dict[str, Any], source: str = "bangumi", source_id: Optional[str] = None) -> Subject:
        pass
    
    @staticmethod
    async def find_by_source(db: AsyncSession, source: str, source_id: str) -> Optional[Subject]:
        pass
    
    @staticmethod
    async def find_by_id(db: AsyncSession, subject_id: int) -> Optional[Subject]:
        pass
```

**主要方法**:
- `save()`: 保存或更新 Subject 数据
- `find_by_source()`: 根据数据源和 ID 查找
- `find_by_id()`: 根据 ID 查找

### 9.3 Collection Repository

**文件**: [repositories/collection_repo.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/repositories/collection_repo.py)

```python
class CollectionRepo:
    @staticmethod
    async def save(db: AsyncSession, user_id: int, subject_id: int, collection_data: Dict[str, Any]) -> Collection:
        pass
    
    @staticmethod
    async def find_by_user_and_subject(db: AsyncSession, user_id: int, subject_id: int) -> Optional[Collection]:
        pass
    
    @staticmethod
    async def find_by_user(db: AsyncSession, user_id: int, subject_type: Optional[int] = None) -> list[Collection]:
        pass
```

**主要方法**:
- `save()`: 保存或更新 Collection 数据
- `find_by_user_and_subject()`: 根据用户和条目查找
- `find_by_user()`: 根据用户查找所有收藏

### 9.4 使用 Repository

在 Service 层中使用 Repository：

```python
from app.repositories import SubjectRepo, CollectionRepo

async def sync_user_collections(username: str, db: AsyncSession, subject_type: Optional[int] = None) -> int:
    for item in items:
        subject = await SubjectRepo.save(db, item)
        await CollectionRepo.save(db, user_id, subject.id, item)
```

---

## 10. 开发规范

### 10.1 代码风格

- 遵循 PEP 8 规范
- 使用类型注解 (Type Hints)
- 函数和类使用 docstring 文档
- 变量命名使用蛇形命名法 (snake_case)
- 类名使用帕斯卡命名法 (PascalCase)

### 10.2 异步编程规范

- 所有数据库操作使用异步方法
- 使用 `async/await` 语法
- 避免阻塞操作
- 正确处理异常和回滚

### 10.3 错误处理

- 使用 HTTPException 返回 HTTP 错误
- 记录详细的错误日志
- 提供友好的错误信息
- 正确处理数据库事务回滚

### 10.4 安全规范

- 敏感信息不记录到日志
- 使用环境变量管理配置
- JWT 密钥使用强随机值
- 输入数据验证和清理

---

## 11. 部署流程

### 11.1 环境要求

- Python 3.9+
- PostgreSQL 13+
- Redis 6+

### 11.2 安装依赖

```bash
pip install -r requirements.txt
```

### 11.3 配置环境变量

创建 `.env` 文件：

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/otakuneko
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=your-openai-api-key
DEBUG=False
```

### 11.4 初始化数据库

```bash
python -m app.db.database
```

### 11.5 启动服务

```bash
uvicorn app.main:app --reload
```

### 11.6 生产部署

使用 Gunicorn + Uvicorn：

```bash
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

---

## 附录

### A. 常见问题

#### Q1: 如何重置缓存？
```python
from fastapi_cache import FastAPICache
await FastAPICache.clear()
```

#### Q2: 如何切换到内存缓存？
```python
from fastapi_cache.backends.inmemory import InMemoryBackend
FastAPICache.init(InMemoryBackend(), expire=60)
```

#### Q3: JWT token 过期时间如何配置？
在 `core/security.py` 中修改 `ACCESS_TOKEN_EXPIRE_MINUTES`。

### B. API 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### C. 性能优化建议

1. 合理使用缓存，避免过度缓存
2. 数据库查询添加索引
3. 使用连接池
4. 异步处理耗时操作
5. 分页返回大数据集

---

**文档版本**: v2.0.0  
**最后更新**: 2025-12-30  
**维护者**: OtakuNeko Team
