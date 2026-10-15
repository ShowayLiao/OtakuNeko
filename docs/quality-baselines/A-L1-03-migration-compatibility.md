# A-L1-03｜迁移、回退与 schema 兼容

证据已无损整理为 [ZIP 归档](A-L1-03-evidence.zip)；各原始 XML/JSON 链接均指向归档中的同名条目，原路径、SHA-256 和 JUnit 计数见 [证据索引](A-L1-03-evidence-index.json)。下文历史命令保留当时的输出路径。

后续唯一约束与生成列整改的最新验证见 [约束整改报告](A-L1-03-constraint-remediation.md)（992 passed / 1 skipped；SQLite 反序 53、PostgreSQL 反序 23）。下文保留历史阶段结果。

最新审查整改与最终回归见 [schema 接管整改报告](A-L1-03-adoption-guards.md)（983 passed / 1 skipped；SQLite 反序 45、PostgreSQL 反序 22）。下文保留各阶段历史证据。

更新：2026-10-15。后续已完成 PostgreSQL 验证，最新跨数据库结果见 [PostgreSQL 补充报告](A-L1-03-postgres-validation.md)（974 passed / 1 skipped；PG 反序18通过）。以下保留 SQLite 阶段证据与当时的限制。

Capability：L1｜Agent CI 与评测体系 v1。

## 结果

SQLite 支持范围内的空库完整升级、当前未版本化本地库接管、业务数据读写、回退/再升级、旧 Trace 读取和失败隔离均通过。最终全量后端回归 **956 passed / 8 skipped / 0 failed**；反序 **40 passed**。PR/Commit 未执行。

用户先授权测试和报告，随后明确授权“继续修复”数据库初始化/迁移路径。本次是独立工程任务，没有活动 Harness Batch，不伪造 Batch 记录。起始分支 `feature-harness`，HEAD `d1c16876e9a1d8870637a37b92e81d49a66dbb18`，普通检出；本轮已有的 6 个未提交 A-L1-03 测试/证据文件均来自同一任务，已保留。没有提交、推送、部署、生产数据库操作或 TickTick 更新。

## 源码根因与修复

首次空库演练确认 `e567b858f91b::upgrade` 在没有建表的情况下为 collection 建索引，子进程退出 1：`no such table: main.collection`。历史脚本还引用已弃用的 user 表和 collection.subject_id；本地 init_db 则只调用当前模型 create_all，未记录迁移版本。

- 新增 `alembic/versions/a10300000001_establish_business_schema.py`，作为原根 revision 的前置基线，显式建立五张业务表。原有 revision ID 和 head `c7d1e4f8a2b6` 保留。
- `app/db/migration_snapshot.py` 固定当前业务/接管契约，不在运行时导入 SQLModel 或当前模型。后续 schema 演进须新增 revision，不能修改这个快照来追随模型变化。
- `app/db/migration_compatibility.py` 在写 DDL 前检查已有表的列、类型、nullability、主键、唯一键、外键、检查约束和索引，并预检 Agent 表组完整性。默认值不作为接管的逐字段等值判据；支持的是当前本地 schema 的结构契约，不声明任意同名表都兼容。
- 已有完整且兼容的当前本地表组被接管，保留其数据；不调用 stamp head，不重建现存表。旧的三个业务增量在完整当前业务布局下复用基线字段/索引，回退也保留它们。
- Memory、scheduler、Trace、interactive Run 增量升级仅在完整表组通过检查后复用已有表，否则执行真实历史 DDL；不完整或不匹配的组被拒绝。
- Trace 回退直接按子表→父表删除表，表自身拥有的索引一并删除，兼容 ORM 创建与 migration 创建两种已支持的索引命名。
- `app/db/database.py::init_db` 通过同一连接运行真实 Alembic；`alembic/env.py` 支持外部连接，避免嵌套 asyncio.run，CLI 路径在 finally 释放引擎。真实本地启动与容器 CLI 共用迁移链。
- `backend/README.md` 记录支持范围、失败处理、在线反射限制和破坏性回退边界。

## 回归覆盖

- `test_database_startup.py`：真实 init_db 在同一内存连接上初始化两次，核验业务/Agent 表及 Alembic head，验证幂等和实际初始化入口。
- `test_database_bootstrap.py`：空库不 stamp、完整 CLI 升级、五张业务表与当前 metadata 的结构比较，以及 User/Subject/Collection/Schedule 的真实 ORM 写入和读取；回退到业务基线后再升级仍保留业务数据。
- 同文件验证现有未版本化本地库接管、重复升级和回退/再升级。create_all 只用于构造已有本地库 fixture，不用于补齐空库目标 schema。未知旧布局和不完整 Agent 表组被拒绝，schema 与行数据不变，允许仅留下空 alembic_version 表。
- `test_migration_compatibility.py`：真实 Alembic 及 SqlTraceStore 验证无 schema_version 的 Trace 经升级、回退和再升级后可读，默认 legacy version=1，并保留匿名/跨用户隔离。真实 DecisionParser 接受省略版本和 v1，拒绝 v2 后继续接受合法 v1。
- 中途失败使用独立 marker 表上的索引名冲突，真实 DDL 创建 agent_run/agent_invocation 后失败，revision 未推进；记录残留 schema，核验后续独立干净库迁移成功及失败临时目录删除、父环境/settings 不变。没有把 SQLite DDL 失败声称为整个 revision 原子回滚。

## 失败证据与整改

[最初历史链失败](A-L1-03-evidence.zip) 保留修复前事实；不代表修复后状态。该探针外层 Python 退出 0 表示确认失败并清理，内部 Alembic 退出 1。

- [初始化红灯](A-L1-03-evidence.zip)：退出 1，1 failed；缺少 alembic_version。修复后同一断言通过。
- 初版 CLI 三个测试落盘时生产修复已经开始，未将其事后运行伪称为修复前红灯。空库首次探针和真实初始化红灯提供独立修复前证据。
- 第一轮修复 Review 发现两个 medium：接管库 Trace 回退找不到旧索引；部分 Agent 表组在后续拒绝前产生 DDL。对应[整改红灯](A-L1-03-evidence.zip)退出 1、2 failed。修复后完整 CLI 测试 4 passed，原断言保留并通过。
- [最终 CLI 证据](A-L1-03-evidence.zip)、[最终全量证据](A-L1-03-evidence.zip)、[最终反序证据](A-L1-03-evidence.zip)保存真实执行状态；中途迁移失败的安全化 properties 保存在反序/全量 JUnit 中。

早期探针曾因 uv 切换目录后重复拼接路径，以及 sqlite3 context manager 未显式关闭连接，分别退出 1；修正后探针退出 0且临时库已清理。这些工具错误不是生产根因。类型检查曾在新增测试发现 7 个注解问题，格式检查发现 2 个文件需格式化；均已修正，最终检查结果如下。

## 最终验证命令

均从仓库根目录执行；`--disable-warnings` 只隐藏详情，不表示消除了警告。

| 命令 | 退出码 | 结果 |
|---|---|---|
| `uv run --directory backend pytest -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-repaired-regression-junit.xml -o junit_family=legacy` | 0 | 956 passed / 8 skipped / 0 failed / 419 warnings；70.29s |
| `uv run --directory backend pytest tests/acceptance/test_database_bootstrap.py tests/acceptance/test_database_startup.py tests/acceptance/test_migration_compatibility.py tests/memory/test_migration.py tests/acceptance/test_run_persistence.py tests/trace/test_sql_store.py tests/harness/test_decision_parser.py -q --tb=short --disable-warnings --reverse-test-order --junitxml=../docs/quality-baselines/A-L1-03-repaired-reverse-junit.xml -o junit_family=legacy` | 0 | 40 passed / 0 skipped / 0 failed / 47 warnings；19.47s |
| `uv run --directory backend pytest tests/acceptance/test_database_bootstrap.py -q --junitxml=../docs/quality-baselines/A-L1-03-bootstrap-cli-junit.xml -o junit_family=legacy` | 0 | 4 passed |
| `uv run --directory backend ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `uv run --directory backend mypy` | 0 | Success，316 source files |
| `uv run --directory backend ruff format --check app/db alembic tests/acceptance/test_database_startup.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_migration_compatibility.py` | 0 | 16 files already formatted |

最终矩阵 unit=647，integration=317，db=183，api=75，postgres=7；维度可重叠，不能相加当作总用例数。8 个跳过为 7 个 PostgreSQL opt-in 用例，以及需 RUN_LIVE_BANGUMI_TESTS=1 的公网检查。警告为现有 Pydantic 配置和 SQLModel execute 等弃用警告。

补充文件检查：git diff --check、git diff --stat 和完整 git diff 均已执行（退出 0）；10 个 tracked 文件及18个新增文件共28个任务文件逐项核对。文档引用扫描 `rg -n 'standard-agent-harness-reference|harness-execution|BATCH-[0-9]+' AGENTS.md docs` 退出 0，521 行匹配。Git 现有 core.autocrlf 产生 LF/CRLF 提示，没有全仓格式化。辅助空白检查初次误将红灯 JUnit 中的原始堆栈空格当作源码问题（退出 1），改为仅检查 Python/Markdown/JSON，保留原始 XML 失败证据不改写。

首次验证阶段的专项3、反序35和全量951/8 skipped 证据仍保留为 `A-L1-03-migration-junit.xml`、`A-L1-03-reverse-junit.xml` 和 `A-L1-03-regression-junit.xml`；修复迭代中的 green/focused XML 为中间结果，最终以 repaired 文件为准。

## Review 与验收

最终独立 Review：pass；修复阶段 rounds=2；findings=[]；无未处理的 medium 或更高问题。第一轮两项 medium 已按真实失败回归完成整改。审查者只读核对完整 diff、新增源码、报告和 JUnit，未重跑测试；主代理完成集成检查。

- 接入真实后端路径：已完成，涵盖真实本地初始化、CLI、SQL 数据读取和版本 parser。
- 测试与失败证据：已保留，覆盖修复前失败、Review 失败、修复后回归。
- 指标、回归结论与下一步：已输出。SQLite 支持范围内迁移失败不污染后续用例；本任务在声明的 SQLite 支持范围内决策为 Accept。
- 不据此完成整个 L1 Capability，也不更新 TickTick。未提交、未创建 PR。

## 限制与下一步

仅支持空库及经固定结构校验的当前本地/业务 schema。历史 user 表、collection.subject_id 复合布局、缺少 source 等未知旧业务布局会明确报 unsupported_business_schema，需要单独定义转换；本次不猜测映射、不丢弃旧数据。已有版本记录本身不证明 schema 完整，也未声称自动修复任意错误 stamp。

没有启用专用 PostgreSQL 测试数据库；代码包含 PostgreSQL 类型定义，但不能据此宣称其线上迁移已验证。接管需要在线反射，没有提供离线 --sql 支持；多 Worker recovery 不在范围内。
未运行前端门禁（无前端修改）、独立模型 Eval（无模型行为修改，完整 pytest 包含现有 evaluation 回归），也未做生产迁移或部署。下一步优先在专用 PostgreSQL 测试库跑同类 fresh/adoption/rollback 回归，再根据真实旧库快照定义转换任务。

## 回滚

代码回滚须整体撤销本任务的初始化、env、历史 revision 接管逻辑和新增基线/helper，同时移除新增测试/文档；不能只删除基线而保留旧根 down_revision 指向。若已运行迁移，先备份并检查 alembic_version；旧代码不认识 a10300000001，不应直接覆盖后启动。

数据回退：`downgrade a10300000001` 保留业务数据，但删除后续 Agent 表及其数据；`downgrade base` 还会删除五张业务表。生产回退须从事先备份恢复或按明确方案操作，本轮未执行。SQLite 中途失败可留下 DDL，测试通过丢弃失败临时库隔离，生产失败库不能盲目重跑或 stamp。
