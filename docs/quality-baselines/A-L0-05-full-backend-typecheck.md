# A-L0-05｜后端全量类型覆盖

## 范围与实现

基准为 `feature-harness` 普通检出，起点 commit `736917769cf1c7e9bcf64ccdd10ca9061f31cec5`；开始时工作区干净。本任务不是 Harness Batch，没有创建 Batch execution record。

`backend/pyproject.toml` 的 Mypy `files` 现在覆盖 `app`、`tests`、`alembic`、`scripts` 和根目录的 `__init__.py`。CI 的 `backend-quality-baseline` job 通过 `backend/scripts/check_type_baseline.py` 执行全量 Mypy，再独立运行 deptry。门禁将每条错误按“相对路径、错误码、错误信息”归一化，忽略行号和 Windows/Linux 路径分隔符，并与 `backend/typecheck-baseline.json` 中的出现次数比较。新增错误、同类错误次数增加、受检文件数下降、输出无法解析或 Mypy 异常退出都会阻断 CI。既有错误减少可以通过；人工审核后应同步收紧基线。豁免是精确错误指纹，没有按文件或错误码整体关闭 Mypy。

## 基线与失败证据

首次 `app tests` 扩围运行退出 **1**：286 个文件、494 条错误。随后纳入迁移及脚本目录；`uv run --locked --offline --directory backend mypy --no-pretty app tests alembic scripts __init__.py` 退出 **1**：298 个文件、74 个报错文件、498 条错误。全量原始输出保存在 [`A-L0-05-initial-mypy-failures.txt`](A-L0-05-initial-mypy-failures.txt)；可机读豁免清单有 256 个唯一指纹及各自次数。498 条中 `app` 有 31 条，`tests` 有 463 条，`alembic` 与 `scripts` 各有 2 条。数量最多的错误码为 `arg-type` 206、`call-arg` 151、`union-attr` 75。此前默认门禁只覆盖 85 个源文件且无错误；全量门禁覆盖 298 个文件，增加 213 个文件。

豁免代表既有类型债务：生产代码的可空性、传参和 MCP transport 类型，迁移及脚本的 SQLAlchemy 属性类型，以及测试替身与真实协议、旧 `AgentTask(metadata=...)` 调用和动态 fixture 类型。清单逐项固定路径、错误码、信息和数量；它不证明报错处的运行时行为正确。下一轮应先收敛 `app` 的 31 条，再处理迁移/脚本的 4 条，最后按 `tests` 的 `call-arg`、`arg-type` 和 `union-attr` 分组修复。每次修复后重跑全量检查并删除相应清单项；任何新增豁免都应在评审中说明原因、数量和后续处理目标。

新增错误探针在临时 `backend/tests/_typecheck_gate_probe.py` 中加入 `value: int = "new type error"`。全量门禁报告 299 个文件、499 条错误，指出 `tests/_typecheck_gate_probe.py [assignment] +1`，退出 **1**；探针文件随后删除。门禁单元测试还验证了错误次数增加、路径归一化、摘要计数不一致和覆盖文件数下降。

## 验证

以下命令使用锁定离线 uv 环境与仓库内缓存执行；`DEBUG=false` 用于避免本机继承的非布尔 `DEBUG` 值影响 Settings。退出码取自真实命令；快速评测报告位于 `backend/.runtime/evaluation/fast.json`，不是远端 CI Run。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv run --locked --offline --directory backend python scripts/check_type_baseline.py` | 0 | 298 个文件；498 条既有错误，0 条新增 |
| `uv run --locked --offline --directory backend pytest tests/test_type_baseline.py -q` | 0 | 2 passed；1 条本机 pytest cache 写入警告 |
| `uv run --locked --offline --directory backend ruff check app tests scripts/check_type_baseline.py` | 0 | 无违规 |
| `uv run --locked --offline --directory backend ruff format --check scripts/check_type_baseline.py tests/test_type_baseline.py` | 0 | 2 个文件符合格式 |
| `uv run --locked --offline --directory backend deptry . --no-ansi` | 0 | 扫描 175 个文件，无依赖问题 |
| `uv run --locked --offline --directory backend pytest -q --disable-warnings` | 0 | 800 passed、1 skipped、306 warnings |
| `uv run --locked --offline --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |

未运行前端 lint、typecheck、test、build：本任务未修改前端代码或协议。未运行远端 GitHub Actions：没有创建 PR 或 push 的授权。

CI YAML 已由本地 PyYAML 解析，包含 `software`、`backend-quality-baseline`、`harness`、`benchmark` 四个 job，类型门禁步骤为 `uv run --locked python scripts/check_type_baseline.py`，解析退出 **0**。按 `docs/code-review.md` 审查了完整改动、原始失败输出与豁免清单；本任务没有新发现的 blocker、critical、high 或未处理 medium Finding，本地 Review verdict 为 **pass**。尚需远端 CI 验证 Windows/Linux 间 Mypy 输出是否完全一致。

## 回归结论与下一步

本地全量门禁可运行且阻断新增类型错误；后端测试、lint、依赖检查与快速评测没有观察到回归。当前 Mypy 原生命令仍会因 498 条既有错误退出 1，因此“全量类型覆盖”表示全量扫描和精确债务门禁，并不表示后端已零类型错误。下一步是按上述分组修复债务、收紧 `typecheck-baseline.json`，再在获得 PR 或 push 授权后检查远端 `backend-quality-baseline` Run。

回滚只需撤销本任务的 CI、Mypy 配置、门禁脚本/测试、基线和本报告改动；无数据库、依赖或外部状态变更。
