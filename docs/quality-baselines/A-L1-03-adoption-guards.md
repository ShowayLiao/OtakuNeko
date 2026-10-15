# A-L1-03｜schema 接管审查整改

证据已无损整理为 [ZIP 归档](A-L1-03-evidence.zip)；各原始 XML/JSON 链接均指向归档中的同名条目，原路径、SHA-256 和 JUnit 计数见 [证据索引](A-L1-03-evidence-index.json)。下文历史命令保留当时的输出路径。

后续唯一约束与生成列整改的最新验证见 [约束整改报告](A-L1-03-constraint-remediation.md)（992 passed / 1 skipped；SQLite 反序 53、PostgreSQL 反序 23）。下文保留历史阶段结果。

日期：2026-10-15。本报告覆盖最新三项审查问题的整改，替代此前报告中的最终回归状态。历史过程见 [SQLite 主报告](A-L1-03-migration-compatibility.md) 与 [PostgreSQL 报告](A-L1-03-postgres-validation.md)。

分支 `feature-harness`，HEAD `d1c16876e9a1d8870637a37b92e81d49a66dbb18`；独立 A-L1-03 工程任务，无活动 Harness Batch。保留同一任务此前全部未提交修改。未提交、推送、创建 PR、部署、访问生产数据库或更新 TickTick。

## 问题与修复

| 审查问题 | 实际风险 | 修复 |
|---|---|---|
| 同名、同列、同 unique 的部分索引被当作完整索引 | 用户名唯一性不完整，后续查询或写入失败 | `migration_compatibility.validate_table` 检查方言 WHERE 谓词；固定快照仅允许无条件索引 |
| CHECK 归一化对整个字符串去空格并转小写 | `'EPISODIC'`、`'epi sodic'` 被误当成 `'episodic'`，合法业务写入失败 | 按 SQL token 比较，仅归一化引号外的关键词大小写和空白；引号内内容原样保留 |
| 仅检查整数主键列名，不检查自动生成能力 | SQLite WITHOUT ROWID 或 PG 移除 SERIAL 默认值后，普通 ORM 插入失败 | SQLite 检查独立主键索引，拒绝不具备 ROWID alias 的布局；PG 检查反射的 autoincrement / identity |

真实入口仍为 `init_db -> Alembic supplied connection` 与 Alembic CLI；校验在现有表接管及业务 DDL 前运行。没有新增 revision、修改业务数据或使用写入探针。CHECK 比较服务于固定快照，不声称实现任意 SQL 表达式的语义等价判定。

## 失败证据与回归

新增 SQLite 测试通过真实 Alembic CLI 分别提交部分唯一索引、CHECK 大小写、CHECK 内部空白和 WITHOUT ROWID 四种不兼容 schema。修复前四项均未被拒绝；修复后均在版本推进前拒绝，完整业务 schema、索引 DDL 和 fixture 行数据与运行前一致，允许 Alembic 留下空版本表。格式变化但字面量不变的正例仍成功升级到 head，ORM 可省略整数 id 写入。

新增 PostgreSQL 测试在真实 PostgreSQL 16.15 上分别验证部分唯一索引、两种 CHECK 字面量和移除 id 生成器，四项修复前均失败、修复后通过。现有 PG fresh/adoption/rollback、业务 CRUD、旧 Trace 读取、失败事务隔离和约束反射回归一并执行。

| 证据 | 退出码 | 结果 |
|---|---|---|
| [SQLite RED](A-L1-03-evidence.zip) | 1 | 4 failed / 1 passed；真实缺陷，原断言未弱化 |
| [PostgreSQL RED](A-L1-03-evidence.zip) | 1 | 4 failed；均为预期拒绝没有发生 |
| [SQLite 专项 GREEN](A-L1-03-evidence.zip) | 0 | 12 passed / 3 warnings |
| [PostgreSQL 专项 GREEN](A-L1-03-evidence.zip) | 0 | 15 passed / 5 warnings |
| [全量后端](A-L1-03-evidence.zip) | 0 | 983 passed / 1 skipped / 0 failed / 421 warnings；79.68s |
| [SQLite 反序](A-L1-03-evidence.zip) | 0 | 45 passed / 47 warnings；22.23s |
| [PostgreSQL 反序](A-L1-03-evidence.zip) | 0 | 22 passed / 962 deselected / 23 warnings；10.97s |

全量唯一跳过项为需要 `RUN_LIVE_BANGUMI_TESTS=1` 的公网集成；PostgreSQL 22 项全部真实运行。警告主要为既有 Pydantic / SQLModel 弃用提示，未删除警告或失败测试。早期 SQLite 测试夹具曾用字符串写入 DateTime，修正为 datetime 后重新采集 RED；初次夹具失败不计作生产缺陷证据。格式检查首次发现新测试排版问题，格式化后复查通过。

## 完整验证命令

均从仓库根目录执行。PostgreSQL 命令前通过进程环境设置指向本任务独立临时库的 `TEST_POSTGRES_URL`，临时凭据没有写入仓库或输出日志。

```powershell
uv run --directory backend pytest tests/acceptance/test_schema_adoption_guards.py -q --junitxml=../docs/quality-baselines/A-L1-03-guards-sqlite-red-junit.xml
uv run --directory backend pytest tests/acceptance/test_postgres_adoption_guards.py --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-guards-postgres-red-junit.xml
uv run --directory backend pytest tests/acceptance/test_schema_adoption_guards.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_migration_compatibility.py -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-guards-sqlite-green-junit.xml
uv run --directory backend pytest tests/acceptance/test_postgres_adoption_guards.py tests/acceptance/test_postgres_migrations.py tests/acceptance/test_postgres_schema_reflection.py --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-guards-postgres-green-junit.xml
uv run --directory backend pytest --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-guards-regression-junit.xml -o junit_family=legacy
uv run --directory backend pytest tests/acceptance/test_schema_adoption_guards.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_database_startup.py tests/acceptance/test_migration_compatibility.py tests/memory/test_migration.py tests/acceptance/test_run_persistence.py tests/trace/test_sql_store.py tests/harness/test_decision_parser.py --reverse-test-order -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-guards-sqlite-reverse-junit.xml -o junit_family=legacy
uv run --directory backend pytest --run-postgres -m postgres --reverse-test-order -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-guards-postgres-reverse-junit.xml -o junit_family=legacy
uv run --directory backend ruff check app tests alembic scripts __init__.py
uv run --directory backend mypy
uv run --directory backend ruff format --check app/db alembic app/models/collection.py app/models/subject.py tests/acceptance/test_database_startup.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_migration_compatibility.py tests/acceptance/test_postgres_migrations.py tests/acceptance/test_postgres_schema_reflection.py tests/acceptance/test_schema_adoption_guards.py tests/acceptance/test_postgres_adoption_guards.py
```

最后三项各自退出 0：lint 无问题、mypy 321 个源码文件无问题、23 个文件格式正确。没有前端修改，因此未运行前端门禁；无模型行为改动，未另行运行模型 Eval，全量 pytest 包含现有 evaluation 回归。

## 隔离、清理与回滚

本轮使用独立带任务标签的 PostgreSQL 16 容器、随机 localhost 端口、tmpfs 数据目录和专用 `otakuneko_guard_test` 数据库。每例独立 UUID schema，测试 finally 释放连接并清理 schema；SQLite 使用独立临时文件和子进程环境。反序验证覆盖拒绝后继续执行合法用例。

[清理证据](A-L1-03-evidence.zip) 确认残余 test schema=0、public 表=0、本轮临时容器和凭据文件均删除；未使用持久卷。未操作开发库、生产库或全局 Docker 引擎。

本轮修复仅收紧接管前校验，不需要数据回滚；若要撤销本轮修复，应整体恢复校验 helper 到本轮开始前状态并移除两个新增 guard 测试，会重新引入三个缺陷。整个 A-L1-03 的代码/数据库回滚边界仍见主报告：回退到业务基线会删除 Agent 表，回退 base 会删除业务表。SQLite 中途 DDL 失败仍可能留下部分 DDL；测试丢弃失败临时库，不声称整个 revision 原子回滚。未知历史 schema 继续明确拒绝，须另行定义转换。

## Review、验收与下一步

Review: pass；本轮修复后独立 review rounds=1，findings=[]，deferred findings=[]。Reviewer 只读审查完整 tracked diff、全部新增生产代码、七个 acceptance 测试文件、三份报告、JUnit 和清理证据；未重跑测试，独立核对 JUnit 计数。没有未处理的 medium 或更高问题。

验收：真实后端路径已接入；失败与通过证据均保留；指标和回归结论已输出。工程验证与独立 Review 均通过，当前固定快照支持范围内结论为 Accept，迁移失败不污染后续用例。下一步是交付当前 diff 供用户验收；Commit/PR 尚未执行，仍需明确授权。不据此完成整个 L1 Capability，不修改外部项目状态。

最终文件检查：git diff --check、git diff --stat、git diff 均退出 0（core.autocrlf 有既有 LF/CRLF 提示）；全部 48 个 untracked 文件已逐类验证，Python AST、JSON、XML 解析和 Markdown 本地链接检查退出 0，未改写原始失败 XML。12 个 tracked 修改与 48 个新增文件全部属于 A-L1-03。文档引用扫描 rg 退出 0，522 行匹配。最终工作区未暂存，分支与 HEAD 未改变。
