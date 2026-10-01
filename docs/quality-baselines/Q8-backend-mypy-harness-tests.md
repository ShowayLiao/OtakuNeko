# Q8｜其余 Harness 测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch。既有 A-L0-08 与 Q1–Q7 修改均保留。

Q8 前为 113 条 / 37 个报错文件 / 298 个受检文件；Q8 后为 **89 条 / 29 个报错文件 / 298 个受检文件**。八个 Q8 文件的 24 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 13 个已消失指纹、共 24 条；门禁实际与许可均为 89，`checked_files` 仍为 298。

修改文件：计划列出的八个 `backend/tests/harness/` 文件和 `backend/typecheck-baseline.json`。可空 checkpoint/run 在访问前做运行时断言；测试 Capability 对齐真实基类；Provider adapter 补齐流式端口且意外调用立即失败；动态方法替换使用 `monkeypatch.setattr`，Pydantic 非法状态测试保留真实 `model_validate`。取消、超时、授权、结果归一化和持久化断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 89 errors / 29 files / checked 298；Q8 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 89、许可 89 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `pytest -q --disable-warnings tests/test_type_baseline.py` | 0 | 2 passed；新增诊断及覆盖收缩门禁测试保留 |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q8 完整 diff Review：**pass**，2 轮；首轮将可静默结束的 fake stream 改为意外调用即失败，并完成格式修复；复核后无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q8 决策：**Accept**；总体清零目标：**Iterate**。本次请求止于 Q8；下一轮 Q9 尚未实施。回滚本轮八个测试文件和对应 13 个精确指纹即可；无外部副作用或数据库变更。
