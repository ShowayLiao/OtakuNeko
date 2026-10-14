# A-L1-02｜业务 Service 与数据模型测试

日期：2026-10-14。关联 Capability：L1｜Agent CI 与评测体系 v1。
本次是普通工程任务，没有活动 Harness Batch，不创建 Batch 执行记录。
起始分支：`feature-harness`；起始 HEAD：`054db201e5055a1701c01f559bcfc56d5f8f0a2b`。
普通检出，初始工作区干净。未提交、未推送、未创建 PR；未修改 TickTick。

## 范围与真实路径

- `backend/tests/services/test_core_service_db.py`：真实 Collection Service / ScheduleService → Repository → 隔离 SQLite；CRUD、空结果、可信 principal 注入、跨用户读写拒绝、重复时间规则。
- `backend/tests/models/test_business_models.py`：Collection、Schedule、Subject 的 SQL 唯一键及 rollback、JSON 落库与公开 schema 往返；UserRead 密码字段排除；输入边界及独立默认容器。
- `backend/tests/api/test_schedule_contract.py`：真实 `/api/v1/schedules/` 路由装配 → JWT 认证 → Dispatcher / Policy / Capability → Service → Repository。只有读取故障注入测试替换 Service，以验证 500 映射；认证和资源授权均不被 mock。
- `backend/app/api/v1/endpoints/schedules.py::create_schedule/update_schedule`：进入 Dispatcher 前使用 `model_dump(mode="json")`。只修复两个入口的时间序列化；不改变权限、schema、数据库或业务规则。

复用 `backend/tests/conftest.py` 的内存 SQLite、隔离 cache 和 ASGI fixture。fixture 不运行应用 lifespan。所有用户和数据均为合成数据，JWT 由 pytest 进程的临时密钥签发，不保留 token 或真实用户内容。
现有统计、条目、Bangumi、qB 和用户画像测试由完整回归继续验证；新增重点为收藏与排班，不声称每个 Service 分支已有全覆盖。

## 修复前失败证据

执行：`uv run --directory backend pytest tests/api/test_schedule_contract.py tests/models/test_business_models.py -q --tb=short --disable-warnings`。
退出码 **1**；**46 passed / 2 failed / 0 skipped / 87 warnings**。

| 测试 | 期望 | 实际 |
| --- | --- | --- |
| `test_schedule_create_serializes_and_injects_principal` | POST 返回 201，落库归属认证用户 | 502，`Schedule operation was not completed` |
| `test_schedule_owner_time_update_serializes_for_dispatcher` | PUT 返回 200，时间更新落库 | 502，`Schedule operation was not completed` |

根因证据：`ScheduleCreate` / `ScheduleUpdate` 把输入解析为 `datetime.time`；原路由使用 Python 模式 `model_dump`；`ScheduleCapability.actions` 声明时间为 JSON string；`normalizer._json_type_matches` 对 string 要求 `isinstance(value, str)`；`Dispatcher.dispatch` 将校验失败返回 `invalid_request`，路由映射为 502。修复位于 HTTP → Dispatcher 的序列化边界，没有放宽输入校验。
两个失败测试保留普通强断言，没有 skip、xfail 或改为期待 502。

调试期间另有测试假设错误：首轮 API 测试遗漏 `/api` 前缀造成 19 failed；模型测试把 CollectionRead 当作公开 ORM id 造成 1 failed。已按实际源码纠正；这些不计为生产缺陷。
完整 mypy 首轮退出码 1，新增两个测试文件共 107 个类型错误；涉及 Optional ID 收窄和 Pydantic 构造签名，修正后需以最终门禁为准。

## 验证与指标

基线：`uv run --directory backend pytest tests/services tests/repositories tests/api/test_collections_query_bounds.py -q`，退出码 **0**，**63 passed / 0 failed / 0 skipped / 68 warnings**。
修复后首轮新增测试：`uv run --directory backend pytest tests/api/test_schedule_contract.py tests/models/test_business_models.py tests/services/test_core_service_db.py -q --tb=short --disable-warnings`，退出码 **0**，**69 passed / 0 failed / 0 skipped / 126 warnings**（后来追加两项 Service 用例）。
完整后端首轮：`uv run --directory backend pytest -q --tb=short --disable-warnings`，退出码 **0**，**946 passed / 0 failed / 8 skipped / 416 warnings**（追加用例前）。

最终新增 **71 项**：Service 23、API 22、模型/输入 schema 26。全部计入最终全量测试，未增加 skip 或 xfail。

| 最终验证命令 | 退出码 | 结果 |
| --- | --- | --- |
| `uv run --directory backend pytest -q --tb=short --disable-warnings` | 0 | 948 passed / 0 failed / 8 skipped / 419 warnings，52.02 秒 |
| `uv run --directory backend mypy` | 0 | 310 个源码文件无类型错误 |
| `uv run --directory backend ruff check app tests` | 0 | All checks passed |
| `uv run --directory backend ruff format --check app/api/v1/endpoints/schedules.py tests/api/test_schedule_contract.py tests/models/test_business_models.py tests/services/test_core_service_db.py` | 0 | 4 个文件符合格式 |
| `uv run --directory backend pytest tests/api/test_schedule_contract.py tests/models/test_business_models.py -q --tb=short --disable-warnings --reverse-test-order` | 0 | 48 passed / 0 failed / 0 skipped / 96 warnings |
| `uv run --directory backend pytest tests/services/test_core_service_db.py -q --tb=short` | 0 | 23 passed / 0 failed / 0 skipped / 53 warnings |
| `git diff --check` | 0 | 无空白问题 |
| `git diff --stat` | 0 | 已跟踪生产改动 1 个文件、4 行新增 / 2 行删除；另外 4 个新增文件通过 status 与全文审查核对 |
| `rg -n "standard-agent-harness-reference\|harness-execution\|BATCH-[0-9]+" AGENTS.md docs` | 0 | 520 行匹配；为缩短终端输出管道至 `Measure-Object -Line` |

最终全量矩阵：unit=647，integration=309，db=176，api=75，postgres=7。维度可重叠，不可直接相加。
8 个跳过项的源码条件为 7 个 PostgreSQL opt-in 用例，以及 `tests/mcp/test_stdio_e2e.py::test_live_tools_call_anime_search` 要求 `RUN_LIVE_BANGUMI_TESTS=1` 的公网检查。本次未启用这些外部条件。
警告为现有 Pydantic class Config 弃用、SQLModel execute 建议等；不将 `--disable-warnings` 当作消除警告。Git 另提示 core.autocrlf 的 LF → CRLF 转换，diff 没有全文件换行改动。

## 审查与决策

独立 reviewer 只读审查完整 tracked diff、三个新测试文件及本报告；实现者检查集成结果。
Review verdict：**pass**；rounds：**1**；findings：**[]**。独立审查者已复核最终报告及命令证据，未发现 blocker/critical/high/medium。

- 接入真实后端路径：已满足；Service 走真实 Repository，HTTP 走真实认证及受控写路径。
- 测试与失败证据：已满足；两个失败测试在修复前退出 1、修复后退出 0，断言保留，失败统计见上文。
- 指标、回归结论与下一步：已输出。当前任务建议 **Accept**；完整回归无新增失败。
- L1 整体 Capability 的验收仍需结合其余 AI Action，不能只凭本任务将 L1 标记完成。
- 下一步：在专用本地 PostgreSQL 测试数据库上扩展本次新增模型/Service 用例，再继续下一项 L1 工作。现有完整测试的 7 个 PostgreSQL 维度用例未启用；新增用例当前只请求 SQLite fixture。
- PR/Commit：未执行；用户未授权提交、推送或创建 PR。

## 限制与回滚

- 没有提供覆盖率百分比；指标是执行用例数量及通过/失败/跳过结果，不把用例数量等同于代码覆盖率。
- PostgreSQL 未启用专用测试数据库，不证明本次新增唯一键测试已经在 PostgreSQL 上执行。
- 未运行前端门禁：无前端变更。未运行生产服务、迁移或部署。
- 未单独执行 Agent Eval：本次不改变 Agent loop、评测数据集或模型行为；完整 pytest 包含现有 evaluation 与 Harness 回归。
- 回滚仅需撤销本任务两个序列化调用和移除三个新增测试文件及本报告；无 schema/数据迁移、无外部副作用。但撤销序列化修复会恢复日程时间字段的 502 缺陷。