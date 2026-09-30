# A-L0-01 后端依赖与质量命令基线实施计划

> **面向 AI 代理的执行说明：** 在当前工作区执行本计划；保留已有用户修改，不创建 Batch execution 记录，不提交或推送。

**目标：** 固定后端 Python/uv 运行时、开发工具依赖和可重复质量命令，并保留真实基线结果、失败证据与未运行项。

**范围：** `backend/pyproject.toml`、`backend/uv.lock`、现有 `.github/workflows/ci.yml` 的后端步骤，以及新增的基线报告。业务代码、数据库、生产部署和现有无关修改不在范围内。

**技术基线：** Python 3.11（仓库已有 `backend/.python-version`）、uv 0.10.10、uv lock/sync、pytest、Ruff、mypy、deptry。

## 任务 1：固定后端项目元数据与开发工具

**文件：**

- 修改：`backend/pyproject.toml`
- 生成：`backend/uv.lock`

- [x] 在 `[tool.uv]` 中增加 `required-version = "==0.10.10"`，保留现有索引配置。
- [x] 将 `mypy`、`deptry` 加入 `dev` dependency group；通过 uv 重新生成锁文件，锁文件中的解析版本作为实际执行版本。
- [x] 增加首期类型检查范围和稳定选项：`app/harness`、`app/capabilities`、`app/memory`、`app/trace`，启用未类型化函数体检查、错误码显示和未使用 ignore 检查。
- [x] 不改动业务源码以制造类型检查通过；若基线存在既有类型错误，保留命令和失败证据。

## 任务 2：把固定命令接入真实后端 CI 路径

**文件：**

- 修改：`.github/workflows/ci.yml`

- [x] 在所有后端 job 中显式使用 Python 3.11 和 uv 0.10.10。
- [x] 将后端安装与质量命令统一为锁定执行：`uv sync --locked --dev`、`uv run --locked pytest`、`uv run --locked ruff check app tests`。
- [x] 在不隐藏失败的前提下验证 mypy/deptry 是否达到可作为 CI 门禁的基线；现有代码导致非零退出，已保持命令在报告中可复现，并明确不把失败伪装成通过。

## 任务 3：保存 A-L0-01 基线报告

**文件：**

- 创建：`docs/quality-baselines/A-L0-01-backend-quality-baseline.md`

- [x] 记录声明版本、实际工具版本、精确命令、每条命令的退出码、通过/失败/跳过数量和警告。
- [x] 记录首次失败证据：缺少项目级 mypy/deptry、默认 uv cache 无权限、pip 不在 uv 环境等事实；区分环境失败与仓库失败。
- [x] 记录回归结论、当前指标、未运行项目及原因、下一步和回滚方式。
- [x] 报告只引用真实源码路径和真实执行结果，不写入 Secret、完整用户数据或 raw provider payload。

## 任务 4：验证与审查

- [x] 在可写的任务缓存目录下执行锁文件检查、锁定同步、pytest、Ruff、mypy 和 deptry，保留退出码。
- [x] 运行 `git diff --check`、`git diff --stat` 和路径/命令引用检查。
- [x] 审查完整未提交 diff，确认没有覆盖用户已有修改、业务代码变化、生成物或超出范围的依赖。
- [x] 不创建 commit；交接时列出 changed files、命令结果、已知失败、回归结论和下一步。
