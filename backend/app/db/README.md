# DB 模块 — 数据库引擎

## 模块简介

数据库连接管理与初始化模块。提供 SQLAlchemy 异步引擎、会话工厂、以及 FastAPI 依赖注入的会话生成器。支持 SQLite（本地）与 PostgreSQL（生产）双模式自动切换。

## 核心功能

| 功能 | 实现 |
|------|------|
| 异步数据库引擎 | `create_async_engine` — 自动适配 SQLite / PostgreSQL |
| 会话工厂 | `AsyncSessionLocal` — SQLAlchemy 异步会话 |
| 依赖注入 | `get_session()` — FastAPI Depends 用 async generator |
| 表结构初始化 | `init_db()` — 启动时自动建表 |

## 文件结构说明

```
db/
├── __init__.py   # 包入口（待实现）
└── database.py   # 引擎 & 会话配置 ([源码](database.py))
```

### database.py — 数据库引擎 ([源码](database.py))

- **智能引擎创建**：
  - SQLite 模式：自动添加 `check_same_thread=False`
  - 日志 `echo=False`（避免 SQL 日志刷屏）
- **全局单例**：`engine` + `AsyncSessionLocal` 均为模块级变量
- **`get_session()`**：FastAPI 依赖注入用 async generator，请求结束自动关闭会话
- **`init_db()`**：调用 `SQLModel.metadata.create_all` 自动建表（本地模式便捷）

## 依赖关系

**配置来源**：
- `app.core.config.settings.DATABASE_URL` — 动态决定 SQLite 或 PostgreSQL 连接串

**被谁调用**：
- `main.py` → `init_db()` + `get_session`（via FastAPI Depends）
- 所有 API 路由 → `Depends(get_session)`
- 所有 Service/Repository → 通过函数参数注入的 `AsyncSession`

**调用谁**：
- `app.core.config` — settings.DATABASE_URL
