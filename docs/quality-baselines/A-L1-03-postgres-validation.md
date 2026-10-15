# A-L1-03｜PostgreSQL 迁移兼容验证

证据已无损整理为 [ZIP 归档](A-L1-03-evidence.zip)；各原始 XML/JSON 链接均指向归档中的同名条目，原路径、SHA-256 和 JUnit 计数见 [证据索引](A-L1-03-evidence-index.json)。下文历史命令保留当时的输出路径。

后续唯一约束与生成列整改的最新验证见 [约束整改报告](A-L1-03-constraint-remediation.md)（992 passed / 1 skipped；SQLite 反序 53、PostgreSQL 反序 23）。下文保留历史阶段结果。

最新审查整改与最终回归见 [schema 接管整改报告](A-L1-03-adoption-guards.md)（983 passed / 1 skipped；SQLite 反序 45、PostgreSQL 反序 22）。下文保留各阶段历史证据。

日期：2026-10-15。关联 [A-L1-03 主报告](A-L1-03-migration-compatibility.md)。
用户在 SQLite 阶段完成后明确要求按建议执行 PostgreSQL 验证。本次继续同一独立任务，不创建 Harness Batch、不修改 TickTick；分支与起始 HEAD 仍为 `feature-harness` / `d1c16876e9a1d8870637a37b92e81d49a66dbb18`。此前本任务的全部修改和证据保留；没有提交、推送、PR、部署或生产迁移。

## 最终结果

启用专用 PostgreSQL 的完整后端回归：**974 passed / 1 skipped / 0 failed**，退出 0。全部 PostgreSQL 用例反序：**18 passed**，退出 0。真实 Cloud 配置的 Alembic CLI 升级 → 回退业务基线 → 再升级均退出 0，业务数据保留。最终独立 Review：pass；PostgreSQL 阶段 rounds=2；findings=[]，无未处理的 medium 或更高问题。审查者未重跑测试，核对完整源码增量、执行记录、JUnit、CLI 和清理 JSON；主代理完成集成检查。

## 环境与隔离

实际服务器为 **PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2)**，使用本机已有 postgres:16 镜像。Docker 最初未运行，本轮启动后台引擎，创建带 A-L1-03 标签的独立容器、随机 localhost 端口、tmpfs 数据目录和随机临时凭据。数据库为专用 `otakuneko_migration_test`；没有连接开发或生产数据库。

- 保留 `validate_postgres_url` 的本地 host、postgresql+asyncpg 驱动、*_test 库名和禁止 URL options 检查。
- 各 pytest 用例在 UUID schema 中设置独立 search_path、使用 NullPool。fresh case 不调用 create_all；只有模拟已存在的当前本地库才用 create_all fixture。
- finally 释放连接并 DROP 对应 schema，核验 namespace 已移除；失败事务与下一干净 schema 分开。
- pytest 通过真实 Alembic supplied-connection 路径执行。另行用真实 `python -m alembic` 子进程及 Cloud 环境配置验证 CLI 的新建连接路径。仅在该专用容器数据库上临时设置 schema search_path，finally 恢复并删除 schema。
- 凭据仅供进程和临时文件使用，不写仓库或 JUnit。没有输出环境变量或数据库 URL。

[清理证据](A-L1-03-evidence.zip)：剩余 test UUID schema=0、public 表=0、数据库 search_path override=0；本任务容器和临时凭据文件均已删除。Docker 后台引擎保持运行。

## 发现与修复

1. PostgreSQL 的 UNIQUE 约束还会在 get_indexes 中反射为底层索引。校验忽略带 duplicates_constraint 的重复索引，唯一约束仍单独严格校验；新增缺失 UNIQUE 的拒绝测试证明没有放宽契约。
2. scheduler revision `bf40dc9e653e` 的 enabled BOOLEAN DEFAULT 1 被 PostgreSQL 拒绝；改为 `sa.true()`，SQLite 仍保存真值。
3. 当前模型的 Collection.updated_at、Subject.last_sync 默认值带时区，而既有列为 TIMESTAMP WITHOUT TIME ZONE。新增 `app/db/types.py::UTCNaiveDateTime`，仅在绑定这两列时将 aware datetime 转为 UTC naive。既有 schema、行数据、Python/API 侧传入值均不改写，显式 naive 值保留；真实 +09:00 输入验证 UTC 持久化。
4. 完整回归发现自定义 sa_column 遗漏 Core insert 的默认值，使既有 SubjectRepo 批量写入失败。已为两个 Column 显式保留原默认 factory，同时保留 Field 的 factory；未删除或弱化原测试。
5. PostgreSQL 接管现在核验外键引用 schema 以及原生 Enum 的标签顺序/schema，拒绝跨 schema 身份引用和同名错误枚举。
6. PG FLOAT 默认等价于 FLOAT(53)，反射成 DOUBLE PRECISION；校验做对应归一化，显式 REAL 仍保持 REAL，新增精度降低的拒绝测试。
7. PostgreSQL 会规范化 CHECK 的类型 cast 和 ANY 表达式。固定快照保存两条 agent_memory CHECK 的 PostgreSQL 规范形式并严格比较，不仅比较约束名或忽略表达式；ALTER CHECK 上限后仍明确拒绝。

上述更改不引入新 head 或数据转换 revision；物理列类型保持原契约。不可变快照只增加其固定 CHECK 契约的 PG 规范表达，不随 ORM 运行时变化。

## 用例与失败证据

新增 `tests/acceptance/test_postgres_migrations.py` 四个真实迁移场景：

- 空 schema 完整升级，业务结构与 ORM CRUD，回退业务基线后再升级，数据一致。
- 当前未版本化全量 schema 接管、重复升级、业务数据和无 schema_version 的 Trace 保留。
- 迁移创建的旧 Trace 跨升级/回退/再升级后由真实 SqlTraceStore 读取，验证匿名及跨用户隔离。
- 注入索引冲突让 interactive migration 真正中途失败；异常退出事务后 revision 未推进、目标表不存在，原 marker 不变。随后独立干净 schema 正常迁移，核验正确目标索引和 marker 不存在。PG 事务回滚与 SQLite 部分 DDL 残留分别断言，不将其混为一谈。

新增 `tests/acceptance/test_postgres_schema_reflection.py` 七个场景：当前业务结构通过接管、缺失唯一约束拒绝、错误枚举拒绝、跨 schema 外键拒绝、非 UTC 时间实际写入读取、变更 CHECK 拒绝、REAL 精度降低拒绝。加上原有七个 opt-in PostgreSQL 用例，最终共18项。

保留的失败与过程证据：

- [首次 PG 探针](A-L1-03-evidence.zip)：schema 反射误拒绝、隔离 schema 已清理。
- [反射红灯](A-L1-03-evidence.zip)：1 failed；修正底层索引反射后1 passed 的绿色证据另存。
- [迁移红灯](A-L1-03-evidence.zip)：4 failed，均为 BOOLEAN DEFAULT 1。
- 修复 Boolean 后实际运行曾出现3 failed：两个 ORM 时间绑定错误和一个测试误判合法目标索引的错误断言。测试改为核验正确表上的 status 索引，不通过删除迁移约束伪造通过。该中间 XML 后被同名最终4 passed 文件覆盖，不将其当作独立保存的红灯文件；上述失败事实记录于本报告。
- [PG 审查红灯](A-L1-03-evidence.zip)：2 failed / 2 passed；枚举和跨 schema 外键原来未拒绝。最终该文件对应全部7项绿色证据见 [PG 审查回归](A-L1-03-evidence.zip)。
- [精度红灯](A-L1-03-evidence.zip)：1 failed；REAL 被误接管，修复后原断言通过。
- [首次全量红灯](A-L1-03-evidence.zip)：1 failed / 972 passed / 1 skipped，既有批量写入回归；[定向回归](A-L1-03-evidence.zip)35 passed。
- [真实 CLI 证据](A-L1-03-evidence.zip)：三个子进程退出 0，业务行保留、最终 head 正确、schema 清理已核验。
- [最终完整回归](A-L1-03-evidence.zip)、[最终 PG 反序](A-L1-03-evidence.zip)是最终判据。`A-L1-03-postgres-final-junit.xml` 的17项记录发生于追加 REAL 回归之前，属于中间结果，不代表最终用例总数。

## 最终命令与指标

从仓库根目录执行，先在该进程设置经过校验的 TEST_POSTGRES_URL（不在记录中保存值）：

| 命令 | 退出码 | 结果 |
|---|---|---|
| `uv run --directory backend pytest --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-all-databases-junit.xml -o junit_family=legacy` | 0 | 974 passed / 1 skipped / 0 failed / 421 warnings；82.71s |
| `uv run --directory backend pytest --run-postgres -m postgres --reverse-test-order -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-postgres-reverse-junit.xml -o junit_family=legacy` | 0 | 18 passed / 957 deselected / 0 skipped / 23 warnings；10.65s |
| `uv run --directory backend pytest tests/acceptance/test_postgres_migrations.py --run-postgres -q --junitxml=../docs/quality-baselines/A-L1-03-postgres-green-junit.xml -o junit_family=legacy` | 0 | 四项迁移测试通过 |
| `uv run --directory backend pytest tests/acceptance/test_postgres_schema_reflection.py --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-postgres-review-green-junit.xml -o junit_family=legacy` | 0 | 七项接管/时间/精度检查通过 |
| `uv run --directory backend ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `uv run --directory backend mypy` | 0 | Success，319 source files |
| `uv run --directory backend ruff format --check app/db app/models/collection.py app/models/subject.py alembic tests/acceptance/test_database_bootstrap.py tests/acceptance/test_database_startup.py tests/acceptance/test_migration_compatibility.py tests/acceptance/test_postgres_migrations.py tests/acceptance/test_postgres_schema_reflection.py` | 0 | 21 files already formatted |

文件与文档检查：`git diff --check`、`git diff --stat` 和相关完整 diff 已执行，退出 0；全部49个任务文件（12 tracked、37新增）已核对来源、源码空白和冲突标记、文档链接及 JSON/XML 可解析性。原始红灯 XML 中的堆栈空白保留，不改写失败证据。最终 JUnit 核验为975项、0 failures、1 skipped；无捕获的 system-out/system-err 元素。文档引用扫描退出 0、522行匹配。

全量矩阵：unit=647，integration=328，db=194，api=75，postgres=18；维度可重叠。唯一 skip 是需 RUN_LIVE_BANGUMI_TESTS=1 的公网测试。现有 Pydantic/SQLModel 弃用警告未消除，不将 disable-warnings 当作消除警告。

辅助命令曾有 Docker port Go-template 在 PowerShell 中转义错误；从同一任务标签容器的 JSON inspect 恢复端口，未重复创建容器。一次额外探针工具调用因自动审批超时未执行，随后用独立测试工具已获得相同诊断。新增校验的 mypy 类型收窄问题用 NoReturn 修正；格式检查失败后已重新格式化且最终通过。

## 决策、边界与回滚

迁移失败不污染后续用例、真实后端路径、失败证据和指标均已满足；在 SQLite 和 PostgreSQL 16.15 的声明范围内决策为 Accept，不代表所有 PostgreSQL 大版本或生产库已验证。
不运行前端门禁（无前端修改）、独立模型 Eval（没有模型行为更改，完整 pytest 包含现有评测回归）或生产操作。没有将未知旧业务布局自动转换的能力，也不支持离线 --sql。

下一步是部署前备份和在目标部署版本/真实旧库脱敏快照上复核；不直接运行生产迁移。回滚仍按主报告整体撤销初始化/迁移接管逻辑，不单独移除前置 revision；新增时间类型回滚会重新暴露原 PostgreSQL aware/naive 写入错误。代码回滚不会恢复已由 downgrade 删除的 Agent 数据，数据库必须按备份方案恢复。
