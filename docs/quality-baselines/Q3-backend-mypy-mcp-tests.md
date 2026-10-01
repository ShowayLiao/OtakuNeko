# Q3｜MCP 协议与客户端测试类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。本轮是质量轮次，不是 Harness Batch。Q1、Q2 和预检前的 A-L0-08 修改均保留。

Q3 前为 338 条 / 61 个报错文件 / 298 个受检文件；Q3 后为 **269 条 / 56 个报错文件 / 298 个受检文件**。五个 Q3 测试文件的 69 条诊断全部消失，原生全量 Mypy 退出 1。精确基线删除 10 个已消失指纹、共 69 条；门禁实际与许可均为 269，`checked_files` 仍为 298。

修改文件：`backend/tests/mcp/test_stdio_e2e.py`、`test_server.py`、`test_protocol_hardening.py`，以及 `backend/tests/agents/mcp/test_adapter.py`、`test_integration.py` 和 `backend/typecheck-baseline.json`。stdio E2E 通过运行时断言确认真实子进程流存在，再保留原有退出码、协议错误、超时和 EOF 检查；协议响应在索引前确认非通知响应。测试替身实现实际 `MCPTransport` 异步契约。

| 命令后缀（锁定离线 uv 环境） | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 269 errors / 56 files / checked 298；Q3 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 269、许可 269 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、306 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；Git 有 LF/CRLF 提示 |

Q3 完整 diff Review：**pass**，1 轮；无 blocker、critical、high 或未处理 medium Finding。前端检查与完整 Eval 未运行：无前端修改，完整 Eval 需要供应商凭据。Q3 决策：**Accept**；总体目标：**Iterate**。下一轮 Q4。回滚本轮五个测试文件和对应 10 个精确指纹即可；无外部副作用或数据库变更。
