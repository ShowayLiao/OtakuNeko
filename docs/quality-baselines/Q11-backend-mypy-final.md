# Q11｜后端 Mypy 清零最终验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch；既有 A-L0-08 与 Q1–Q10 修改均保留。

Q11 前为 19 条 / 10 个报错文件 / 298 个受检文件；Q11 后为 **0 条 / 0 个报错文件 / 298 个受检文件**。十个 Q11 文件的 19 条诊断全部消失，原生全量 Mypy 退出 0。精确基线删除最后 16 个指纹、共 19 条，现为 `errors=[]`、`checked_files=298`；新增错误和覆盖收缩的两项门禁测试继续通过。

修改文件：计划列出的五个 `backend/tests/agents/`、两个 `backend/tests/capabilities/`、两个 `backend/tests/evaluation/`、一个 `backend/tests/proactive/` 文件和 `backend/typecheck-baseline.json`。Agent 测试网关实现完整协议并产生真实流式终态；Dispatcher 拒绝直接执行 specialist 的强断言保留。Judge 错误脱敏、Capability 不可变性和调度 lease 恢复断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 0 | 0 errors / 0 files / checked 298 |
| `python scripts/check_type_baseline.py` | 0 | 实际 0、许可 0 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `pytest -q --disable-warnings tests/test_type_baseline.py` | 0 | 2 passed；新增错误与覆盖收缩均被拒绝 |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q11 完整本轮 diff Review：**pass**，2 轮；首轮测试网关原型的流式终态不符合真实协议，目标测试失败，修复后针对性 25 个 Agent 测试和全量回归均通过。Q1–Q11 各轮 diff 与最终累计范围审查未发现 blocker、critical、high 或未处理 medium Finding。完整 Eval 未运行：`full.yaml` 使用生产 Target 与在线 Judge，需要供应商凭据；前端检查未运行：本计划无前端修改。

清零能力最终决策：**Accept**。起点 369 条 / 69 个报错文件 / 298 个受检文件，终点 0 / 0 / 298；相对最初 498 条累计减少 498 条。精确基线仍保留全量扫描和新增错误阻断。未提交、未推送、未部署。回滚按 Q1–Q11 报告列出的本轮文件和精确基线变更执行，已有用户工作区修改须保留。
