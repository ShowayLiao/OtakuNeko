# OtakuNeko Backend

OtakuNeko 的后端服务基于 FastAPI、SQLModel/SQLAlchemy、Alembic 和 `uv`。本地模式使用 SQLite 与内存缓存；Cloud/Docker 模式使用 PostgreSQL，并连接 Redis。Agent Harness、Memory、Trace、Evaluation 和 MCP 等后端能力也位于本目录。

## 环境要求

- Python 3.10 或更高版本（Docker 镜像使用 Python 3.11）
- [`uv`](https://docs.astral.sh/uv/)
- 可选：Docker 与 Docker Compose

后端 Python 依赖以 `pyproject.toml` 和 `uv.lock` 为唯一事实源。`requirements.txt` 仅用于仍依赖 pip 的兼容流程；不要在 `backend/` 中安装或提交 Node.js 依赖，前端依赖由 `frontend/package.json` 和 `frontend/pnpm-lock.yaml` 管理。

## 本地启动

从仓库根目录进入后端目录并同步锁定依赖：

```powershell
cd backend
uv sync --frozen
Copy-Item .env.example .env
```

macOS/Linux 可将最后一条命令替换为 `cp .env.example .env`。首次启动前请检查 `.env`，至少替换 JWT 密钥和实际使用的模型提供商凭据；示例值只适用于本地开发。

初始化或升级数据库，然后启动 API：

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后可访问：

- 健康检查：<http://localhost:8000/health>
- OpenAPI：<http://localhost:8000/docs>
- API v1：`http://localhost:8000/api/v1`

本地模式由 `DEPLOY_MODE=local` 启用，数据库路径由 `SQLITE_FILE` 控制。Cloud 模式需要配置 PostgreSQL、Redis、Checkpoint 和 Provider 出站策略；可用变量及开发默认值见 `.env.example` 与 `app/core/config.py`。

## 数据库初始化与兼容范围

本地启动的 `init_db()` 与上述 CLI 使用同一 Alembic 迁移链，并记录版本；不再以当前 ORM 的 `create_all` 替代升级。Cloud 模式仍在启动 API 前显式执行迁移。

空库由 `a10300000001` 固定业务 schema 基线开始建立。已有的未版本化本地库，仅在现存表的列、类型、主键、唯一键、外键、检查约束和索引满足固定兼容快照时接管；保留数据并逐 revision 前进，不直接 `stamp head`。快照为 `app/db/migration_snapshot.py`，未来模型变化应新增 revision，不能随模型更新这个快照。

更早的 `user` 表、`collection.subject_id` 等未定义转换的结构会报 `unsupported_business_schema`。请保留备份并单独设计数据转换，不要通过删除数据库、手动 stamp 或忽略异常绕过检查。已有版本记录的数据库继续按其 revision 执行；旧版本记录本身不能证明 schema 完整。

操作已有数据库前先备份。`alembic downgrade a10300000001` 保留业务基线，但会删除后续 Agent 表及其中数据；`alembic downgrade base` 还会删除业务表。迁移失败时 SQLite 可能残留部分 DDL，不能把它当作自动完整回滚；生产失败库需从备份恢复或经过审计的修复，测试用失败库应隔离并丢弃。

以上路径已在 SQLite 与隔离的 PostgreSQL 16.15 上完成回归，包含真实 CLI、接管和回退。Collection.updated_at 和 Subject.last_sync 保持无时区 UTC 存储契约，绑定 aware 输入时先归一化为 UTC；不改写已有行数据。当前变更未提供离线 `--sql` 迁移支持，接管检查需要在线反射 schema。

## Docker Compose

从仓库根目录启动完整开发环境：

```powershell
docker compose up --build
```

Compose 会启动 PostgreSQL、Redis、后端、qBittorrent 和前端。后端容器在启动 API 前执行 `alembic upgrade head`。`docker-compose.yml` 中的账号和密码是开发默认值，部署前必须替换，并应通过环境或 Secret 管理注入。

## 测试与检查

以下命令从仓库根目录执行：

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
```

快速 Evaluation：

```powershell
uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml
```

Pytest 只收集 `backend/tests/`。可重复、无需真实外部副作用的测试应放入该目录；需要人工执行的维护工具应放入 `backend/scripts/`，不要在 `backend/` 或仓库根目录散放 `test_*.py`、`check_*.py`。

## 目录结构

```text
backend/
├── alembic/       # 数据库迁移
├── app/           # FastAPI、业务服务与 Agent Harness 源码
├── evals/         # Evaluation 数据集、基线与配置
├── scripts/       # 显式运行的维护脚本
├── tests/         # pytest 测试
├── pyproject.toml # Python 项目与工具配置
└── uv.lock        # 锁定依赖
```

## Git 中不保存的本地文件

以下内容由运行环境、外部 API 或本地工具生成，不属于源码：

- SQLite 数据库及 `-journal`、`-wal`、`-shm` 边车文件；
- Bangumi API 响应、豆瓣导入、qBittorrent 导出等原始 JSON；
- lint 输出、架构预览报告和本地任务绑定信息；
- `.env`、日志、缓存、虚拟环境以及运行时数据。

如果某份外部响应需要成为回归测试，请先移除账号、Token、评论等用户数据，将其缩减为最小、稳定的测试样例，并与对应测试一起放入 `backend/tests/`。
