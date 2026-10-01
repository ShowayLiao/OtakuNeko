# Q5｜审计切换验收测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch。既有 A-L0-08 与 Q1–Q4 修改均保留。

Q5 前为 215 条 / 53 个报错文件 / 298 个受检文件；Q5 后为 **185 条 / 50 个报错文件 / 298 个受检文件**。三个 Q5 文件的 30 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 18 个已消失指纹、共 30 条；门禁实际与许可均为 185，`checked_files` 仍为 298。

修改文件：`backend/tests/acceptance/test_task_post_audit_004_contract.py`、`test_task_post_audit_010_api_cutover.py`、`test_task_post_audit_010_entrypoints.py` 和 `backend/typecheck-baseline.json`。API 直接调用改用真实 `AsyncSession` fixture 与有效的 `UserRead`；Capability、Memory repository/extractor 及 gateway 替身对齐当前契约。意外 synthesis 会明确失败；原有授权拒绝、审批、取消、资源隔离和错误脱敏断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 185 errors / 50 files / checked 298；Q5 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 185、许可 185 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q5 完整 diff Review：**pass**，2 轮；首轮发现 gateway 假成功结果与 repository 宽泛签名，修复并重跑后无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q5 决策：**Accept**；总体目标：**Iterate**。下一轮 Q6。回滚本轮三个测试文件和对应 18 个精确指纹即可；无外部副作用或数据库变更。
