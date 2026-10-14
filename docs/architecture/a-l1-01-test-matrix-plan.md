# A-L1-01 测试矩阵与隔离夹具实施计划

用户已批准增量方案及独立任务实施；不创建 Batch 记录，不提交或同步外部项目。

目标：保留现有布局，定义 unit/integration 层及 DB/API/PostgreSQL 维度，验证真实路由、仓库、外部客户端的隔离与可复现性。

范围：backend/tests/、backend/pyproject.toml、.github/workflows/ci.yml、本任务文档。禁止修改业务实现、迁移、前端、依赖版本和生产配置。

- [x] 运行 API/仓库/服务基线并保留失败原因。
- [x] 先运行 commit、缓存、API 身份隔离、HTTP timeout/未安排请求和 PostgreSQL 目标限制回归的失败版本。
- [x] 在应用导入前固定测试环境；SQLite 显式注册全部模型并 finally dispose；PostgreSQL 仅接受本地专用 *_test 库，逐测试随机 schema，仅清理自身 schema。
- [x] API 使用实际 api_router 与 SQL session，默认保留认证拒绝；HTTP doubles 使用响应/异常队列，拒绝未安排请求，并保留 ASGI transport 与 AsyncClient 类身份。
- [x] 注册 markers、PostgreSQL opt-in 和逆序选项；显式标记既有直接 DB/ASGI 测试，不移动文件。
- [x] CI 添加 PostgreSQL 16 服务和 always JUnit artifacts。
- [x] 验证新回归正常/重复/逆序、完整 pytest、Ruff 和 diff，记录真实退出码与指标。
- [x] Review 完整任务 diff，修复后重跑检查，输出结论及风险。

回滚：恢复本任务修改并删除本任务新增文件，保留已有用户修改。无业务迁移或外部业务写入。
