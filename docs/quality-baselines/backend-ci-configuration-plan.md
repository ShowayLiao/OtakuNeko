# 后端与 CI 配置门禁实现计划

目标：将批准的配置覆盖设计接入阻断式 CI，并用实际错误探针验证。
架构：离线脚本复用应用加载器；actionlint 和 Compose 使用其权威校验器；覆盖脚本汇总 14 个配置路径并拒绝未登记文件。repository-quality 汇总配置 job 的结果。

- [x] Luna 负责 backend/scripts/check_configuration.py 与 backend/tests/test_configuration.py：先新增失败测试，再实现 11 个应用配置路径的离线校验，拒绝错误模板、缺失引用、非法 Schema，输出安全 JSON。
- [x] 协调者负责 backend/scripts/check_configuration_coverage.py、backend/tests/test_configuration_coverage.py、.github/workflows/ci.yml：登记 14 路径与真实校验器结果，新增配置 job、固定 actionlint 版本及摘要阻断规则。
- [x] 统一入口工具探针使用 OS TemporaryDirectory 并自动清理，早期手动探针、工具下载及报告使用忽略的 backend/.runtime/quality/ 目录：actionlint 非法工作流、Compose 非法字段、离线脚本错误配置，记录实际非零退出码。
- [x] 运行 uv run --locked --directory backend pytest；uv run --locked --directory backend ruff check app tests alembic scripts __init__.py；uv run --locked --directory backend ruff format --check app tests alembic scripts __init__.py；uv run --locked --directory backend python scripts/check_type_baseline.py；uv run --locked --directory backend deptry .；真实配置工具命令和覆盖汇总。
- [x] 审查全部变更并更新 docs/quality-baselines/backend-ci-configuration-boundaries.md：完整命令、退出码、失败/跳过、覆盖路径数与部署排除项。未授权提交/远程 CI，故不提交、不触发远程动作，CI 实际运行状态明确 UNKNOWN。

回滚：撤销此次脚本、测试、配置 job 和相关文档修改，不涉及迁移和外部状态。
