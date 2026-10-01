# Q10｜Memory 与 Trace 测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch；既有 A-L0-08 与 Q1–Q9 修改均保留。

Q10 前为 49 条 / 21 个报错文件 / 298 个受检文件；Q10 后为 **19 条 / 10 个报错文件 / 298 个受检文件**。十一个 Q10 文件的 30 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 19 个已消失指纹、共 30 条；门禁实际与许可均为 19，`checked_files` 仍为 298。

修改文件：计划列出的五个 `backend/tests/memory/`、六个 `backend/tests/trace/` 文件和 `backend/typecheck-baseline.json`。测试替身实现真实协议，Trace 事件使用正式枚举，SQLModel 列类型经运行时断言收窄，Memory 字符串输入校验、安全过滤与脱敏断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 19 errors / 10 files / checked 298；Q10 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 19、许可 19 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q10 完整本轮 diff Review：**pass**，2 轮；首轮恢复 Memory 字符串构造校验覆盖，并将 Trace 测试会话纳入异步上下文；重跑后无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q10 决策：**Accept**；总体清零目标：**Iterate**。下一轮 Q11。回滚本轮十一个测试文件和对应 19 个精确指纹即可；无外部副作用或数据库变更。
