# Q4｜主 Runtime 决策与持久化验收测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch。既有 A-L0-08 与 Q1–Q3 修改均保留。

Q4 前为 269 条 / 56 个报错文件 / 298 个受检文件；Q4 后为 **215 条 / 53 个报错文件 / 298 个受检文件**。三个 Q4 文件的 54 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 17 个已消失指纹、共 54 条；门禁实际与许可均为 215，`checked_files` 仍为 298。

修改文件：`backend/tests/acceptance/test_primary_runtime_decision_loop.py`、`test_primary_runtime_canonical_persistence.py`、`test_runtime_single_owner.py` 和 `backend/typecheck-baseline.json`。测试输入使用 Pydantic 的 `task_metadata` 别名；决策模式向 Runtime 传入真实允许的 `None` adapter；gateway、Capability、Dispatcher 与持久化替身对齐当前契约。fake gateway 的意外合成调用明确失败，原有取消、超时、决策拒绝、单一终态、持久化失败、重放及审批恢复断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 215 errors / 53 files / checked 298；Q4 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 215、许可 215 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q4 完整 diff Review：**pass**，2 轮；首轮发现 fake gateway 可为意外合成调用返回成功，修复并重跑后无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q4 决策：**Accept**；总体目标：**Iterate**。下一轮 Q5。回滚本轮三个测试文件和对应 17 个精确指纹即可；无外部副作用或数据库变更。
