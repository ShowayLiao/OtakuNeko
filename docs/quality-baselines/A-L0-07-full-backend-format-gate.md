# A-L0-07｜全后端 Python 格式阻断门禁

## 范围与结果

基于 `feature-harness` 的 `8f83b90d1f6fc1438e6ccd10146a11130f49e8b8`，工作区开始时干净。本次只修改 `.github/workflows/ci.yml`、Ruff 自动格式化的后端 Python 文件和本记录；没有业务实现、依赖或数据库迁移语义变更，也没有活动 Harness Batch。

CI 的 `backend-quality-baseline` job 现在以 `uv run --locked ruff format --check app tests alembic scripts __init__.py` 阻断整个目标范围。原先只检查八个架构目录并上传范围外债务 diff 的步骤已移除。历史记录 `A-L0-02-backend-format-gate.md` 保留原验收时点的事实，不作为当前范围说明。

## 格式债务趋势

以下命令均从仓库根目录执行，Ruff 为锁定的 0.15.12。前三轮使用 `uv run --locked --directory backend ruff format --check app tests alembic scripts` 统计剩余数量；非零退出码表示当轮仍有既有债务。独立 Review 发现该范围遗漏根目录 `backend/__init__.py`，随后将它纳入最终门禁。

| 时点 | 本轮 Ruff 报告重排 | 剩余待格式化 | 已合规 | 当轮检查退出码 | 回归证据 |
| --- | ---: | ---: | ---: | ---: | --- |
| 初始 | — | 140 | 157 | 1 | 工作区干净；与 A-L0-02 的 140 个范围外文件基线吻合 |
| 第 1 轮：模型、仓储、Schema、服务、对应测试、Alembic、scripts | 53 | 87 | 210 | 1 | `ruff check app tests alembic scripts __init__.py`：0；`DEBUG=false pytest tests/services tests/repositories -q`：53 passed，62 warnings，退出 0 |
| 第 2 轮：Agent、API、集成入口与对应测试 | 62 | 25 | 272 | 1 | 同一 Ruff lint：0；`DEBUG=false pytest tests/agents tests/api tests/mcp -q`：198 passed，97 warnings，退出 0 |
| 第 3 轮：evaluation、acceptance、architecture、proactive 测试 | 25 | 0 | 297 | 0 | 同一 Ruff lint：0；`DEBUG=false pytest tests/acceptance tests/architecture tests/evaluation tests/proactive -q`：155 passed，71 warnings，退出 0 |
| Review 修复：补齐根目录 `__init__.py` | 1 | 0 | 298 | 0 | 全范围格式检查含 `__init__.py`；该文件原先仅缺末尾换行 |

首轮未设置 `DEBUG` 的定向 pytest 曾在 collection 阶段退出 1：继承的 `DEBUG=release` 不是布尔值。设置 `DEBUG=false` 后，同一测试范围退出 0；这是测试环境配置要求，不属于格式变更引起的断言失败。

## 最终验证

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv run --locked --directory backend ruff format --check app tests alembic scripts __init__.py` | 0 | `298 files already formatted` |
| `uv run --locked --directory backend ruff check app tests alembic scripts __init__.py` | 0 | `All checks passed!` |
| `$env:DEBUG='false'; uv run --locked --directory backend pytest -q --disable-warnings` | 0 | 800 passed，1 skipped，305 warnings |
| `uv run --locked --directory backend python scripts/check_type_baseline.py` | 0 | 298 个文件、498 个既有类型错误；基线允许 498 个 |
| `uv run --locked --directory backend deptry .` | 0 | 175 个文件；无依赖问题 |
| `uv run --locked --directory backend python -c "import yaml; ..."` | 0 | YAML 可解析，格式步骤为全范围阻断命令 |
| `git diff --check` | 0 | 无空白错误；Git 仅提示 Windows `core.autocrlf` 下 LF 将来可能转为 CRLF |

直接运行 `uv run --locked --directory backend mypy` 退出 1，报告 298 个文件中 498 个既有错误。这不是 CI 的类型门禁；CI 运行的是上表中的 `check_type_baseline.py`，其结果为 0。本次未处理类型债务。

未运行前端 lint、typecheck、test、build 和 Agent Eval：本次没有前端文件或可执行 Python AST 变化；全量后端 pytest、格式、lint、类型基线与依赖检查已覆盖本次变更的直接风险。远端 CI 未触发，因此不能声称远端门禁已通过。

## Review 证据

- 将全部实际产生 Git 差异的 139 个 Python 文件逐一与 `HEAD` 比较：原 138 个文件中完整 AST 有 36 个文件不同，差异来自 Ruff 对文档字符串空白与换行的规范化；忽略文档字符串后，138/138 的 AST 相同，注释 token 多重集也相同。新增的根目录 `__init__.py` 仅补末尾换行；复验的 139/139 个文件可执行 AST 和注释 token 多重集均相同。其余两个 Ruff 报告重排的文件未形成 Git 内容差异。
- 检查完整未提交变更的文件边界：Python 格式文件、CI 配置和本记录；没有用户原有修改、业务补丁、依赖锁文件、Secret、缓存或生成文件混入。格式改动与 CI 行为变更在不同文件中，便于分别审查。
- 独立只读 Review 首轮判定 `changes_required`：全范围门禁遗漏 `backend/__init__.py`，且本记录过早写入 `pass`。补齐范围并复跑检查后，二轮复审确认代码和 CI 门禁通过；发现本记录还保留了待复验文字。现已更新为实际命令结果。尚无远端 CI Run；本记录只陈述本地命令结果。

```yaml
review_result:
  batch: null
  kind: documentation
  verdict: pass
  summary: 全范围格式门禁覆盖 298 个 Python 文件，格式差异未改变可执行 AST 和注释；首轮与二轮 Review 的问题均已修复。
  findings: []
  acceptance_checks:
    task_complete: true
    scope_compliant: true
    tests_verified: true
    architecture_compliant: true
    authorization_checked: true
    side_effects_checked: true
    recovery_checked: true
    compatibility_checked: true
    documentation_consistent: true
    rollback_available: true
  reviewed_commands:
    - command: uv run --locked --directory backend ruff format --check app tests alembic scripts __init__.py
      exit_code: 0
    - command: git diff --check
      exit_code: 0
  reviewed_files:
    - .github/workflows/ci.yml
    - backend/app/
    - backend/tests/
    - backend/alembic/
    - backend/scripts/
    - backend/__init__.py
    - docs/quality-baselines/A-L0-07-full-backend-format-gate.md
  deferred_findings: []
```

## 回滚与后续

本记录编写时尚未创建 PR；本地提交状态以 Git 历史为准。回滚时分别撤销本次 Python 格式差异、`.github/workflows/ci.yml` 的全范围门禁替换和本记录；不要覆盖后续工作区修改。远端 PR/CI 运行证据需在获得创建 PR 的授权并实际触发后补充，不能由本地检查推断。
