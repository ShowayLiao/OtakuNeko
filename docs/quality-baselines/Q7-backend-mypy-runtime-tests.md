# Q7｜Runtime 编排与协调器测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch。既有 A-L0-08 与 Q1–Q6 修改均保留。

Q7 前为 154 条 / 40 个报错文件 / 298 个受检文件；Q7 后为 **113 条 / 37 个报错文件 / 298 个受检文件**。三个 Q7 文件的 41 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 18 个已消失指纹、共 41 条；门禁实际与许可均为 113，`checked_files` 仍为 298。

修改文件：`backend/tests/harness/test_runtime_orchestration.py`、`test_reasoning_forwarding.py`、`test_coordinator.py` 和 `backend/typecheck-baseline.json`。fake gateway 对齐 `ModelGateway` 的结构化推理和流式接口；未使用的操作立即失败。测试持久化替身使用当前 Run、Invocation 和 Event 模型；终态辅助函数接受协变序列。原有推理增量、工具反馈、模型预算、单一终态及跨 Run invocation ID 断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 113 errors / 37 files / checked 298；Q7 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 113、许可 113 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q7 完整 diff Review：**pass**，2 轮；首轮清理了一个不可达的 fake stream 产出分支，复核后无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q7 决策：**Accept**；总体目标：**Iterate**。下一轮 Q8。回滚本轮三个测试文件和对应 18 个精确指纹即可；无外部副作用或数据库变更。
