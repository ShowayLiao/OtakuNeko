# A-L1-03｜唯一约束与生成列接管整改

证据已无损整理为 [ZIP 归档](A-L1-03-evidence.zip)；各原始 XML/JSON 链接均指向归档中的同名条目，原路径、SHA-256 和 JUnit 计数见 [证据索引](A-L1-03-evidence-index.json)。下文历史命令保留当时的输出路径。

日期：2026-10-15。范围为最新审查提出的两项缺陷：SQLite UNIQUE 冲突策略未校验、生成列被当作普通可写列接管。前序历史见 [schema 接管报告](A-L1-03-adoption-guards.md)。本报告给出本轮最终状态；历史失败证据继续保留。

分支 `feature-harness`，HEAD `d1c16876e9a1d8870637a37b92e81d49a66dbb18`。独立 A-L1-03 任务，无活动 Harness Batch。开始时已发现来自另一会话的同目标修复；用户明确确认保留并在此基础上验证、补修。没有撤销这些修改，也不把它们事后伪称为本轮 TDD 实现。

## 修复与验收边界

- 固定快照中的列均为普通列；反射发现 `computed` 时在接管前拒绝。SQLite 与 PostgreSQL 均适用。
- SQLite 反射不提供 UNIQUE 的冲突策略，因此校验读取 CREATE TABLE DDL。隐式 ABORT 与显式 ABORT 等价；REPLACE、IGNORE、FAIL、ROLLBACK 均拒绝，防止静默替换、忽略旧数据或改变错误事务语义。
- DDL 校验需要忽略 SQL 注释，完整识别引号内的标识符和字符串，避免注释绕过或从引号内误读关键字；这不是任意 SQL 等价判定器。
- 不新增 revision，不转换或改写业务数据，不使用数据写入探针。

## 证据说明

前一轮 review 已在独立内存 SQLite 通过真实 Alembic 升级和普通 ORM 写入复现两项缺陷：升级到 `c7d1e4f8a2b6` 后生成列写入失败；UNIQUE ON CONFLICT REPLACE 导致重复写入成功且旧收藏行消失。本轮开始时，简单生成列及 REPLACE 拒绝已存在于用户确认的修改中。新增 RED 只证明本轮仍存在的解析边界缺口，不追溯伪造基础修复前的 JUnit。

## 验证

全部命令从仓库根目录执行。带 `--run-postgres` 的命令通过进程环境使用本任务临时 `TEST_POSTGRES_URL`，凭据不写入仓库或 JUnit。

| 证据 | 退出码 | 指标 |
|---|---|---|
| [解析 RED](A-L1-03-evidence.zip) | 1 | 2 failed / 11 passed；注释 REPLACE 被放行、quoted 关键字 ABORT 被误拒绝 |
| [SQLite GREEN](A-L1-03-evidence.zip) | 0 | 20 passed / 3 warnings；25.10s |
| [PostgreSQL GREEN](A-L1-03-evidence.zip) | 0 | 16 passed / 5 warnings；8.35s |
| [完整后端](A-L1-03-evidence.zip) | 0 | 992 passed / 1 skipped / 0 failed / 421 warnings；95.67s |
| [SQLite 反序](A-L1-03-evidence.zip) | 0 | 53 passed / 47 warnings；35.22s |
| [PostgreSQL 反序](A-L1-03-evidence.zip) | 0 | 23 passed / 970 deselected / 23 warnings；13.21s |

初次夹具将注释放在 UNIQUE 与括号之间，导致 SQLAlchemy 无法反射该唯一约束，正例在冲突策略检查前已被拒绝；[该次运行](A-L1-03-evidence.zip) 为 1 failed / 12 passed，退出 1，保留为夹具调试记录，不作为生产解析根因证据。调整为反射可识别、注释放在 ON 与 CONFLICT 之间后采集上表真正 RED。修复后相同断言全部通过。不能由 SQLAlchemy 反射匹配的结构仍保守拒绝，未为接管放松约束。

最终生产代码用 token 扫描替换裸正则位置查找；注释被忽略，引号包围的内容整体保留，UNIQUE 列列表按 token 平衡括号，不从约束名内部读取策略。原 computed 拒绝保持生效，新增 PostgreSQL 真实生成列测试通过。SQLite 生成列 fixture 通过 bangumi_name 创建合法用户，保留用户与收藏数据一起做失败前后比较。

```powershell
uv run --directory backend pytest tests/acceptance/test_schema_adoption_guards.py -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-constraints-parser-red-junit.xml
uv run --directory backend pytest tests/acceptance/test_schema_adoption_guards.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_migration_compatibility.py -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-constraints-sqlite-green-junit.xml
uv run --directory backend pytest tests/acceptance/test_postgres_adoption_guards.py tests/acceptance/test_postgres_migrations.py tests/acceptance/test_postgres_schema_reflection.py --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-constraints-postgres-green-junit.xml
uv run --directory backend pytest --run-postgres -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-constraints-regression-junit.xml -o junit_family=legacy
uv run --directory backend pytest tests/acceptance/test_schema_adoption_guards.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_database_startup.py tests/acceptance/test_migration_compatibility.py tests/memory/test_migration.py tests/acceptance/test_run_persistence.py tests/trace/test_sql_store.py tests/harness/test_decision_parser.py --reverse-test-order -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-constraints-sqlite-reverse-junit.xml -o junit_family=legacy
uv run --directory backend pytest --run-postgres -m postgres --reverse-test-order -q --tb=short --disable-warnings --junitxml=../docs/quality-baselines/A-L1-03-constraints-postgres-reverse-junit.xml -o junit_family=legacy
uv run --directory backend ruff check app tests alembic scripts __init__.py
uv run --directory backend mypy
uv run --directory backend ruff format --check app/db alembic app/models/collection.py app/models/subject.py tests/acceptance/test_database_startup.py tests/acceptance/test_database_bootstrap.py tests/acceptance/test_migration_compatibility.py tests/acceptance/test_postgres_migrations.py tests/acceptance/test_postgres_schema_reflection.py tests/acceptance/test_schema_adoption_guards.py tests/acceptance/test_postgres_adoption_guards.py
```

lint 退出 0，mypy 321 个文件退出 0，23 个文件格式检查退出 0。类型检查初次发现原有测试中 Constraint 变量与 CheckConstraint 复用导致赋值类型冲突，重命名局部变量后复查通过；没有放宽类型配置或测试断言。

唯一跳过项为需要 `RUN_LIVE_BANGUMI_TESTS=1` 的公网 Bangumi 集成，23 个 PG 用例全部实际运行。421 项警告为既有 Pydantic / SQLModel 等弃用警告，`--disable-warnings` 仅隐藏明细。没有前端或模型行为改动，因此未运行前端门禁和独立模型 Eval；完整 pytest 覆盖现有 evaluation 回归。

## 隔离、回滚与限制

SQLite 使用独立临时文件和子进程配置，拒绝用例比较 DDL、所有 fixture 行和空版本表；正例重复写入必须失败并保留旧行。生成列 fixture 必须通过其源列创建合法用户，避免使用孤儿行伪造兼容数据。

PostgreSQL 使用独立任务标签容器、随机 localhost 端口、tmpfs 和专用 `otakuneko_constraint_test` 数据库，每例 UUID schema；不使用开发或生产数据库。实际 PostgreSQL 为 16.15；[清理证据](A-L1-03-evidence.zip) 确认残余 test schema=0、public 表=0，临时容器和凭据文件均删除，未使用持久卷，未停止全局 Docker 引擎。初次 pg_isready 在实例启动过程中退出 1，稍后就绪检查退出 0；不计作迁移失败。

整个 A-L1-03 的回滚边界继续适用：降级至业务基线会删除后续 Agent 表，降级 base 会删除业务表。SQLite 中途 DDL 失败可能残留 DDL，测试通过丢弃失败临时库隔离，不声称整个 revision 原子回滚。未知历史 schema 的数据转换、生产迁移、多 Worker recovery、前端与模型行为均不在本轮范围。

## Review 与结论

Review: pass；本轮修复后 rounds=1，findings=[]，deferred findings=[]。独立 Reviewer 只读检查完整 tracked diff、4 个新增生产文件、7 个新增测试文件、最终报告及本轮 JUnit/清理证据，未重跑测试，独立核对 JUnit 数量。主代理完成集成与真实执行检查。当前固定快照支持范围内结论为 Accept：两项缺陷及解析边界已修复，拒绝时 schema、fixture 行和版本不变，失败不污染后续用例。用户随后明确授权清理 diff 并创建本地提交；提交标识以包含本报告的 Git commit 为准。没有推送、创建 PR、部署或修改 TickTick。

最终文件验证：git diff --check、git diff --stat、完整 git diff 各退出 0；57 个新增文件（11 Python、4 Markdown、36 XML、6 JSON）已按类型解析并核对 Markdown 本地链接，检查退出 0。保留原始失败 XML 中的堆栈空白，未为通过空白检查改写证据。文档引用 rg 扫描退出 0，522 行匹配。12 个 tracked 修改与 57 个新增文件共 69 个任务文件，均未暂存。LF/CRLF 提示来自既有 core.autocrlf。

本轮仅修改兼容性 helper、两个 guard 测试文件、相关报告和证据；没有改动新的业务或部署范围。本轮无数据转换；如需代码回滚，应仅恢复本轮三个代码/测试文件的增量并保留用户确认的其他修改，这会重新引入已知解析问题，须重新验证。整体任务的数据库降级边界见上文。

## 本地提交收尾

用户明确授权清理 diff 并本地提交。清理只整理报告与证据，不改变已审查的生产代码或测试：42 份原始 XML/JSON 从 1,419,165 字节无损压缩为 186,855 字节 ZIP；每个条目逐字节校验，索引保存原路径、SHA-256 和 JUnit 计数。所有报告链接已更新。完整任务 diff 从 69 个文件收敛为 29 个，历史失败证据没有删除或改写。

提交前重新执行默认后端回归：`uv run --directory backend pytest -q --tb=short --disable-warnings`，退出 0，969 passed / 24 skipped / 419 warnings，83.34s。24 个跳过为 23 个 PostgreSQL opt-in 和 1 个公网 Bangumi 用例。此次没有重新创建 PostgreSQL；代码和测试未改变，前一轮真实 PG 全量 992 passed / 1 skipped、PG 反序 23 passed 的原始证据保留在归档中。

提交前再次运行 `uv run --directory backend ruff check app tests alembic scripts __init__.py`、`uv run --directory backend mypy` 及上文同范围 `ruff format --check`，各退出 0：lint 无问题、mypy 321 个文件无问题、23 个文件格式正确。证据索引、ZIP 校验与报告链接检查全部通过。收尾 Review: pass；没有新增业务改动、未处理 Finding 或新增风险。仅创建本地提交，不推送、不创建 PR。