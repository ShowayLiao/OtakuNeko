# EVAL-001 完善实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用
> superpowers:subagent-driven-development（推荐）或
> superpowers:executing-plans 逐任务实现此计划。步骤使用复选框语法跟踪。

**目标：** 将当前 EVAL-001 草稿完善为离线可重复、阈值可配置、报告可审计并
能在 CI 阻止回归的评测框架。

**架构：** 严格类型和配置位于边界层；Runner 通过 `AgentRuntime` 执行可注入
Adapter；确定性指标、可选 Judge、baseline 和报告彼此解耦。

**技术栈：** Python 3.11、dataclasses、Pydantic、PyYAML、pytest、
GitHub Actions。

---

### 任务 1：严格数据集与核心类型

**文件：**
- 创建：`backend/app/evaluation/types.py`
- 修改：`backend/app/evaluation/dataset.py`
- 修改：`backend/app/evaluation/__init__.py`
- 修改：`backend/evals/datasets/v1.jsonl`
- 测试：`backend/tests/evaluation/test_dataset.py`

- [ ] 先添加失败测试：显式 dataset version、fixtures、assertions、未知嵌套
  字段、缺失字段和所有必需场景。
- [ ] 运行 `uv run pytest tests/evaluation/test_dataset.py -q`，确认因字段/
  场景缺失而失败。
- [ ] 用 Pydantic 严格模型实现 JSONL manifest + case 校验并补齐 v1 fixtures。
- [ ] 重跑测试确认通过。

### 任务 2：配置、Runner Adapter 与确定性指标

**文件：**
- 创建：`backend/app/evaluation/config.py`
- 创建：`backend/app/evaluation/adapter.py`
- 修改：`backend/app/evaluation/metrics.py`
- 修改：`backend/app/evaluation/runner.py`
- 修改：`backend/evals/config/fast.yaml`
- 修改：`backend/evals/config/full.yaml`
- 测试：`backend/tests/evaluation/test_runner.py`
- 创建：`backend/tests/evaluation/test_metrics.py`

- [ ] 先添加失败测试：严格 YAML、tag 过滤、`AgentRuntime` 调用、部分失败、
  schema/evidence/recovery/latency/budget 指标及阈值边界。
- [ ] 运行 Runner/metrics 测试，确认缺失 API 导致预期失败。
- [ ] 实现配置模型、确定性 Runtime Adapter、全套指标和聚合门禁。
- [ ] 重跑测试确认通过。

### 任务 3：Judge、Baseline 与报告

**文件：**
- 修改：`backend/app/evaluation/judge.py`
- 创建：`backend/app/evaluation/reporting.py`
- 创建：`backend/evals/baselines/v1-fast.json`
- 测试：`backend/tests/evaluation/test_judge.py`
- 创建：`backend/tests/evaluation/test_reporting.py`

- [ ] 先添加失败测试：Judge 协议、结构化解析、cache key 隔离、timeout、
  unavailable、baseline 方向/容差/缺失指标、JSON 报告 schema。
- [ ] 运行 Judge/reporting 测试，确认预期失败。
- [ ] 实现最小异步 Judge、显式状态、版本化 baseline 和原子 JSON 报告。
- [ ] 重跑测试确认通过。

### 任务 4：CLI 与 CI 门禁

**文件：**
- 修改：`backend/app/evaluation/runner.py`
- 修改：`backend/pyproject.toml`
- 创建：`.github/workflows/evaluation.yml`
- 创建：`backend/evals/README.md`
- 测试：`backend/tests/evaluation/test_cli.py`

- [ ] 先添加失败测试：fast CLI 成功、阈值回归失败、配置错误失败、报告文件
  生成且不包含密钥。
- [ ] 运行 CLI 测试确认失败。
- [ ] 实现 composition root、模块/脚本入口、CI fast/full jobs 和本地文档。
- [ ] 重跑 CLI 测试确认通过。

### 任务 5：复审、全量验证与提交

**文件：**
- 审查全部 EVAL-001 相关文件。

- [ ] 运行 `uv run pytest tests/evaluation -q`。
- [ ] 运行 `uv run python -m app.evaluation.runner --config evals/config/fast.yaml`。
- [ ] 运行 `uv run ruff check app/evaluation tests/evaluation`。
- [ ] 运行 `uv run pytest tests -q`。
- [ ] 运行 `git diff --check` 并请求独立代码审查。
- [ ] 修复所有 Critical/Important，重复验证。
- [ ] 精确暂存 EVAL-001 文件，排除 `docs/architecture-audit.md`，提交。
