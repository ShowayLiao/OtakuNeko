# Q9｜服务与 API 测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch；既有 A-L0-08 与 Q1–Q8 修改均保留。

Q9 前为 89 条 / 29 个报错文件 / 298 个受检文件；Q9 后为 **49 条 / 21 个报错文件 / 298 个受检文件**。八个 Q9 文件的 40 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 33 个已消失指纹、共 40 条；门禁实际与许可均为 49，`checked_files` 仍为 298。

修改文件：计划列出的八个 `backend/tests/services/`、`backend/tests/api/` 文件和 `backend/typecheck-baseline.json`。测试使用真实 `AsyncSession` 或有明确端口的异步替身；数据库生成的可空 ID 在访问前断言；Pydantic 输入继续通过真实校验，Enum 与服务签名一致。原有资源归属、写入回滚、缓存失败、Bangumi 失败路径和画像断言保留。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 49 errors / 21 files / checked 298；Q9 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 49、许可 49 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、310 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q9 完整 diff Review：**pass**，2 轮；首轮将裸 `AsyncSession()` 改为由 pytest 管理的会话 fixture，重跑后无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q9 决策：**Accept**；总体清零目标：**Iterate**。下一轮 Q10。回滚本轮八个测试文件和对应 33 个精确指纹即可；无外部副作用或数据库变更。
