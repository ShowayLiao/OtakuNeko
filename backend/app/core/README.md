# Core 模块 — 核心基础设施

## 模块简介

提供整个应用的基础设施：配置管理、认证安全、日志系统。
所有其他模块都依赖此模块获取环境配置和日志记录器。

## 核心功能

| 模块 | 功能 | 全局入口 |
|------|------|----------|
| `config.py` | 多环境配置管理（local/cloud 模式自动切换） | `settings` 单例 |
| `security.py` | JWT 令牌 + bcrypt 密码哈希 | `create_access_token`, `decode_access_token`, `get_password_hash`, `verify_password` |
| `logging.py` | 带请求ID追踪的日志系统，支持文件轮转和控制台输出 | `get_logger(name)` |

## 文件结构说明

```
core/
├── __init__.py   # 包入口（待实现）
├── config.py     # 配置管理（Pydantic Settings）
├── logging.py    # 日志系统（RotatingFile + 控制台）
└── security.py   # 安全模块（JWT + 密码哈希）
```

### config.py — 配置管理 ([源码](config.py))

- **类 `Settings`**：继承 `pydantic_settings.BaseSettings`
  - 从 `.env` 文件和环境变量自动读取配置
  - **双模式部署**：通过 `DEPLOY_MODE` 切换
    - `local` → SQLite (`sqlite+aiosqlite:///./local.db`)
    - `cloud` → PostgreSQL (`postgresql+asyncpg://...`)
  - `DATABASE_URL` 为 `@computed_field`，运行时动态计算
  - 包含 JWT_SECRET_KEY（强制校验，无默认值）、CORS_ORIGINS（逗号分隔多域名）、OPENAI_API_KEY、REDIS_URL、qBittorrent 配置等

### logging.py — 日志系统 ([源码](logging.py))

- **类 `LoggingConfig`**：日志配置管理器
  - 日志格式：`时间 - 级别 - 模块 - 请求ID - 消息`
  - 双通道输出：文件（app.log + error.log）+ DEBUG模式下控制台
  - 支持并发安全文件轮转（`ConcurrentRotatingFileHandler`），降级为 `TimedRotatingFileHandler`
  - `RequestContextFilter` 支持请求级 trace ID 注入
- **全局函数**：`get_logger(name)` — 获取配置好的 logger

### security.py — 安全模块 ([源码](security.py))

- JWT 令牌管理：`create_access_token` / `decode_access_token`
  - 使用 HS256 算法，SECRET_KEY 来自 JWT_SECRET_KEY 环境变量（空值时抛 ValueError 阻断启动）
  - Token 有效期 7 天
- 密码管理：`get_password_hash` / `verify_password`
  - 使用 bcrypt 算法

## 依赖关系

```
                    ┌──────────────┐
                    │   main.py    │  ← 启动时读取 settings, init_db, init cache
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         config.py    logging.py   security.py
              │            │            │
              ▼            ▼            ▼
         所有模块      所有模块      api/deps.py
         (settings)   (get_logger)  (auth)
```

**被谁调用**：
- `config.py` → 被 `main.py`, `db/database.py`, `api/deps.py` 等几乎所有模块使用
- `logging.py` → 被所有 services, repositories, agents 等模块使用 `get_logger(__name__)`
- `security.py` → 被 `api/deps.py`（JWT 验证）、`services/user_service.py`（密码哈希）

**调用谁**：
- `config.py`：无内部依赖，仅依赖 `pydantic_settings`
- `logging.py`：无内部依赖，仅依赖 `concurrent_log_handler`（可选）
- `security.py`：依赖 `config.py`（读取 SECRET_KEY）
