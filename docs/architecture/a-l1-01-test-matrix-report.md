# A-L1-01 后端测试矩阵与隔离夹具报告

执行日期：2026-10-13；完成日期：2026-10-14（Asia/Shanghai）。任务：L1｜Agent CI 与评测体系 v1 / A-L1-01。

状态：完成；最终 Review verdict 为 pass。用户批准作为独立任务实施；没有活动 Batch，不创建 Batch execution record。分支 `feature-harness`，起点和当前 HEAD 均为 `31677268e0e684f90329fd2ee63ac2c4c3f69c31`；未提交、未创建 PR、未推送、未同步 TickTick。

## 结果与真实接入

- `backend/tests/matrix_plugin.py::classify_item` 定义互斥 unit/integration 层和可重叠 db/api/postgres 维度，默认由目录、fixture closure 和显式标记确定；矛盾层标记直接报配置错误。既有直接建库和 ASGI 测试补充显式标记，不移动目录。
- `backend/tests/conftest.py` 在应用导入前固定测试配置，隔离宿主 DEBUG、应用 SQLite 文件、checkpoint 和 provider key。每个测试拥有独立 SQLite engine/session；全部模型显式注册，finally 释放 engine。缓存类级存储与锁逐测试重建并清理。
- `backend/tests/isolation_support.py::isolated_postgres_engine` 仅接受 loopback、asyncpg、数据库名以 `_test` 结尾且无 URL options 的测试 URL。每个测试创建 UUID schema，search_path 只指向自身 schema，业务 commit 不影响其他测试，正常或异常退出均清理自身 schema。
- `api_app/api_client` 使用真实 `app.api.api_router`、SQL session 和 ASGI transport，保留认证默认拒绝，结束后清理依赖覆盖。SQLite/PostgreSQL 回归调用 `/api/v1/users/me`，覆盖匿名 401、读取已 commit 用户，以及跨测试相同 ID 无污染。PostgreSQL RunStore 回归覆盖真实持久化、状态转换和用户范围查询。
- `external_http` 使用严格 HTTPX MockTransport 队列；真实 `BangumiClient.get_subject_raw` 覆盖成功、503、timeout 和未安排请求。临时 patch 构造方法，保留 AsyncClient 类身份及显式 ASGI transport；退出后 monkeypatch 恢复。
- CI 的 `software` 与新增 PostgreSQL 16 job 均保存 JUnit，上传步骤为 always；PostgreSQL 已加入 `repository-quality.needs`、结果汇总与失败检查。

## 指标与验证

以下命令从仓库根目录运行；PostgreSQL 命令的 `TEST_POSTGRES_URL` 指向一次性本地 PostgreSQL 16 容器的 `otakuneko_test`，loopback 端口 55431，使用合成测试凭据。

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `uv run --directory backend pytest tests/api/test_collections_write_regression.py tests/repositories tests/services/test_collection_service.py -q`（显式测试环境） | 0 | 基线 26 passed、74 warnings |
| `uv run --directory backend pytest -q --disable-warnings --junitxml=.runtime/a-l1-01/full.xml` | 0 | 877 passed、0 failed、8 skipped、311 warnings；54.89 秒 |
| `uv run --directory backend pytest -q --disable-warnings --reverse-test-order --junitxml=.runtime/a-l1-01/full-reverse.xml` | 0 | 877 passed、0 failed、8 skipped、311 warnings；55.20 秒 |
| `uv run --directory backend pytest --run-postgres -m postgres -q --disable-warnings --junitxml=.runtime/a-l1-01/postgres.xml` | 0 | 7 passed、0 failed、0 skipped、878 deselected、23 warnings；4.87 秒 |
| `uv run --directory backend pytest --run-postgres -m postgres --reverse-test-order -q --disable-warnings --junitxml=.runtime/a-l1-01/postgres-reverse.xml` | 0 | 7 passed、0 failed、0 skipped、878 deselected、23 warnings；4.90 秒 |
| `uv run --directory backend pytest tests/test_isolation_fixtures.py tests/test_matrix_classification.py tests/agents/mcp/test_transport.py tests/test_configuration.py tests/test_configuration_coverage.py -q --disable-warnings --junitxml=.runtime/a-l1-01/final-focused.xml` | 0 | 最终类型/格式与 CI 修正后 83 passed、6 skipped、23 warnings |
| `uv run --directory backend ruff check app tests` | 0 | 无 lint 错误 |
| `uv run --directory backend ruff format --check app tests alembic scripts __init__.py` | 0 | 307 files already formatted |
| `uv run --directory backend python scripts/check_type_baseline.py` | 0 | 307 文件，0 errors，baseline permits 0 |
| `git diff --check` | 0 | 无空白错误 |
| `git diff --stat` | 0 | 已核对变更范围；stat 不包含未跟踪新增文件 |

引用检查命令 `rg -n "standard-agent-harness-reference|harness-execution|BATCH-[0-9]+" AGENTS.md docs` 退出码 0，最终扫描 520 行引用；未伪造 Batch 记录。

矩阵收集数量为 unit **627**、integration **258**，合计 **885**；DB **125**、API **53**、PostgreSQL **7** 是重叠维度，不能相加。正常与逆序运行结果一致。全量默认跳过项为 7 个 opt-in PostgreSQL 用例（已在专用运行中全部通过）及 1 个真实 Bangumi 网络测试（保持 opt-in，未访问真实外部服务）。

JUnit 证据保留于本地忽略目录 [`backend/.runtime/a-l1-01/`](../../backend/.runtime/a-l1-01/)；CI 已配置上传对应软件和 PostgreSQL JUnit artifact。没有启动或发布远程 CI，不宣称托管 CI 已通过。

CI YAML 和 required gate 额外验证：

```powershell
uv run --directory backend python -c "from pathlib import Path; import yaml; w=yaml.safe_load(Path('../.github/workflows/ci.yml').read_text(encoding='utf-8')); j=w['jobs']; assert 'postgres' in j['repository-quality']['needs']; s=j['repository-quality']['steps'][0]; assert 'POSTGRES_RESULT' in s['env'] and 'POSTGRES_RESULT' in s['run']; assert j['postgres']['services']['postgres']['image']=='postgres:16'; print('CI YAML and PostgreSQL required gate verified')"
```

退出码 0。测试后查询 `pg_namespace` 的 `test_%` schema 数量及 public 表数量均为 **0**，退出码 0；核对容器 ID 后执行 `docker rm --force --volumes` 清理本任务容器，退出码 0。

## 失败证据与修正

- 基线首次收集失败：宿主 `DEBUG=release` 无法解析为 bool（退出码 1）；显式测试环境重跑基线通过，最终 conftest 在应用导入前固定测试值。
- 首轮新增回归：6 failed、3 passed、8 fixture errors（退出码 1）；其中缓存第二个参数化用例读取上一个测试数据，根因是 `FastAPICache.reset()` 不清理 InMemoryBackend 类级存储。缺失 SQLite/API/HTTP/PG 夹具按计划补齐，缓存污染修复。
- [`postgres-red.xml`](../../backend/.runtime/a-l1-01/postgres-red.xml)：1 failed、6 passed（退出码 1）；RunStore owner 未在 users 表创建，真实 PostgreSQL FK 拒绝写入。补充测试用户，未关闭 FK 或削弱断言。
- [`full-reverse-red.xml`](../../backend/.runtime/a-l1-01/full-reverse-red.xml)：1 failed、874 passed、8 skipped（退出码 1）；旧 MCP 测试依赖已有 event loop。[`loop-red.xml`](../../backend/.runtime/a-l1-01/loop-red.xml) 在 `asyncio.run` 关闭 loop 后单独复现失败；改为 pytest async await，原 `not found` 断言保持，[`loop-green.xml`](../../backend/.runtime/a-l1-01/loop-green.xml) 通过。
- [`transport-red.xml`](../../backend/.runtime/a-l1-01/transport-red.xml)：1 fixture error（退出码 1）；HTTP double 先初始化后导入 SDK 时，替换 AsyncClient 类导致 subclass TypeError。构造方法 patch 与保留 ASGI transport 的组合回归通过，完整正常/逆序均通过。
- 类型基线曾失败：新增 pending 队列缺少注解（1 error，退出码 1）；添加准确类型后为 0。格式检查曾失败：3 个测试文件待格式化（退出码 1）；仅格式化任务涉及文件后通过。

## Review 与验收

第一轮 verdict 为 changes_required：3 个 medium（遗漏 DB/API 标记、HTTP double transport 覆盖、文档编码）。退出 Review 后修正，第二轮完整代码 Review 为 pass，无新增代码 Finding。第三轮完整任务 diff 与最终证据 Review 为 pass；共 3 轮 Review，无未处理或 deferred Finding。

验收证据：真实路由、数据库模型、RunStore 与外部 Bangumi 客户端已接入；正常/失败/拒绝、commit 隔离与 schema 异常清理均有自动测试。常规与逆序运行一致，失败 JUnit 和最终指标已保留。

## 修改文件

- `.github/workflows/ci.yml`、`backend/pyproject.toml`。
- `backend/tests/conftest.py`、`README.md`、`__init__.py`、`isolation_support.py`、`matrix_plugin.py`、`test_isolation_fixtures.py`、`test_matrix_classification.py`。
- `backend/tests/acceptance/test_harness_baseline.py`、`test_restart_recovery.py`、`test_run_persistence.py`、`test_sse_replay.py`。
- `backend/tests/agents/mcp/test_transport.py`。
- `backend/tests/harness/test_checkpoint.py`、`test_run_store.py`。
- `backend/tests/memory/test_api.py`、`test_migration.py`、`test_sql_repository.py`、`test_sql_repository_sqlalchemy_session.py`。
- `backend/tests/services/test_qb_service.py`、`backend/tests/trace/test_sql_store.py`。
- 本报告与 [`a-l1-01-test-matrix-plan.md`](a-l1-01-test-matrix-plan.md)。

`frontend/FORMAT_CHECK_DECISION.md` 是已有用户修改；`.codex/agents/luna_worker.toml` 在工作期间出现修改，用户已明确确认属于自己的操作。均原样保留，不属于本任务。

## 限制、下一步与回滚

- API fixture 验证真实 router/service/repository，未运行整个应用 lifespan；不证明 scheduler/Redis 启动或生产部署可用。
- PostgreSQL fixture 使用 metadata.create_all，未新增 PostgreSQL Alembic upgrade/downgrade 验收。真实外部 Bangumi live check、前端、完整 Agent Eval 与生产操作未运行：本任务只修改后端测试基础设施与 CI，不改变业务/Harness 行为。
- 当前证明正常/逆序和隔离回归的可复现性，不保证任意随机顺序或全部未来测试。进程被强制杀死时 finally 无法运行；仅可在确认专用测试库后清理遗留 test schema。
- 警告主要为既有 Pydantic 配置与 SQLModel execute 弃用；Git 提示 LF/CRLF 转换，本任务未更改仓库全局行尾配置。
- 下一步：在托管 CI 验收软件/PostgreSQL 两条 required gates 及 artifact；后续单独规划 PostgreSQL migration 与应用 lifespan 测试。
- 回滚：审查并恢复本任务已跟踪文件的改动，删除本任务新增文件；保留上述用户修改。不使用整仓 reset，不涉及业务数据库迁移或外部状态补偿。
