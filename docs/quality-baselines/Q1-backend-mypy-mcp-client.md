# Q1｜MCP 客户端类型债务验收

日期：2026-10-01。分支：`feature-harness`；HEAD：`e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。Q1 是类型质量轮次，不是 Harness Batch。预检时工作区已有 A-L0-08 的五个已修改源码/测试文件、类型基线修改和一份未跟踪报告，以及本轮实施计划；本轮保留了这些既有内容。

## 范围与结果

- 修改 `backend/app/agents/mcp/{adapter,connection_pool,heartbeat,sse_transport,stdio_transport}.py`、对应 `tests/agents/mcp/test_transport.py` 和 `backend/typecheck-baseline.json`。未修改 Harness Batch 目标、Mypy 扫描范围、CI 或依赖。
- 原生全量 Mypy：起点 369 条 / 69 个报错文件 / 298 个受检文件；Q1 后 347 条 / 64 个报错文件 / 298 个受检文件，退出码 1。Q1 五个文件的 22 条诊断全部消失；原生全量退出 0 是 Q11 后的最终验收项。
- 精确许可只删除 Q1 已消失的 15 个指纹、共 22 条；`checked_files` 保持 298，现存许可合计 347。基线门禁退出 0，新增错误与覆盖收缩仍由 `tests/test_type_baseline.py` 拒绝。
- stdio 对缺失进程流、EOF 和关闭状态进行真实检查。读循环结束时结束待处理请求；初始化失败或取消时清理子进程。SSE 对缺失客户端进行检查，初始化失败或取消时关闭 HTTP 客户端。动态 Pydantic 字段仍由 `create_model()` 校验。

## 验证

以下命令从仓库根目录执行，均设置 `UV_CACHE_DIR=.uv-cache`（绝对路径）及适用的 `DEBUG=false`，使用 `uv run --locked --offline --directory backend`。

| 命令后缀 | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 347 errors / 64 files / checked 298；Q1 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | checked 298；实际 347、许可 347 |
| `pytest tests/test_type_baseline.py -q --disable-warnings` | 0 | 2 passed；1 条 pytest cache 权限警告 |
| `pytest tests/mcp/test_stdio_e2e.py tests/agents/mcp/test_transport.py tests/agents/mcp/test_integration.py tests/agents/mcp/test_adapter.py -q --disable-warnings` | 0 | 28 passed、20 warnings |
| `pytest -q --disable-warnings` | 0 | 803 passed、1 skipped、306 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed；报告 `.runtime/evaluation/fast.json` |
| `git diff --check` | 0 | 无空白错误；Git 提示工作树 LF 将转换为 CRLF |

新增的 stdio EOF 与关闭后请求测试先分别以超时和 `AttributeError` 失败；SSE 初始化失败清理测试先因 `aclose()` 未调用失败，修复后纳入全量回归。Review 首轮发现新加的 stdio 读失败日志会记录原始异常；改为仅记录异常类别后重跑全量 pytest、Ruff、格式检查、基线门禁和 fast Eval，第二轮通过。前端检查、完整 Eval 和生产启动未运行：Q1 不涉及前端，完整 Eval 需要供应商凭据，生产操作不在本轮范围内。

## Review 与决定

```yaml
review_result:
  batch: Q1
  kind: quality
  verdict: pass
  rounds: 2
  summary: Q1 的 22 条诊断清零，连接失败与关闭路径有回归测试，范围与基线一致。
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
    - command: uv run --locked --offline --directory backend pytest -q --disable-warnings
      exit_code: 0
    - command: uv run --locked --offline --directory backend ruff check app tests alembic scripts __init__.py
      exit_code: 0
    - command: uv run --locked --offline --directory backend ruff format --check app tests alembic scripts __init__.py
      exit_code: 0
    - command: uv run --locked --offline --directory backend python scripts/check_type_baseline.py
      exit_code: 0
  reviewed_files:
    - backend/app/agents/mcp/adapter.py
    - backend/app/agents/mcp/connection_pool.py
    - backend/app/agents/mcp/heartbeat.py
    - backend/app/agents/mcp/sse_transport.py
    - backend/app/agents/mcp/stdio_transport.py
    - backend/tests/agents/mcp/test_transport.py
    - backend/typecheck-baseline.json
  deferred_findings: []
```

Q1 决策：**Accept**。总体清零目标：**Iterate**，下一轮为 Q2；本轮不提前实施。未解决风险是其余 347 条类型诊断继续按精确基线许可。回滚时仅恢复本轮 MCP 五个文件、对应测试和本轮删除的 15 个指纹；保留预检前已有的 A-L0-08 修改，不涉及外部状态或数据库迁移。
