# Q2｜MCP 服务端类型债务验收

日期：2026-10-01；分支 `feature-harness`；HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`。Q2 是类型质量轮次，不是 Harness Batch。预检确认 Q1 与 A-L0-08 的未提交修改仍在工作区，本轮未覆盖或改写它们。

## 结果

- Q2 前：347 条 / 64 个报错文件 / 298 个受检文件；Q2 后：**338 条 / 61 个报错文件 / 298 个受检文件**。原生全量 Mypy 退出 1，Q2 三个文件的 9 条诊断清零。
- 从 `backend/typecheck-baseline.json` 删除实际消失的 6 个精确指纹、共 9 条；`checked_files` 维持 298。门禁显示实际 338、许可 338，退出 0。
- MCP 幂等缓存形成键之前再次确认可信 `MCPContext.user_id` 与非空幂等键；原有入口认证、侧效应策略、参数校验与资源授权路径保持。工具 schema 区分 Pydantic 模型与 JSON Schema 字典，复制字典后再去掉标题；未知类型显式报错。空 Redis URL 显式进入现有内存缓存回退。
- 本轮修改 `backend/app/agents/registry.py`、`backend/app/main.py`、`backend/app/mcp_server/__init__.py`、`backend/tests/agents/test_registry.py`、`backend/tests/mcp/test_policy.py` 和精确基线。未修改 Q3 及后续轮次文件、依赖、CI 或扫描范围。

## 验证与 Review

命令从仓库根目录执行，使用锁定离线 uv 环境与 `UV_CACHE_DIR=.uv-cache`（绝对路径）；适用时设置 `DEBUG=false`。

| 命令后缀 | 退出码 | 结果 |
| --- | ---: | --- |
| `mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 338 errors / 61 files / checked 298；Q2 文件 0 |
| `python scripts/check_type_baseline.py` | 0 | 实际 338、许可 338、checked 298 |
| `pytest -q --disable-warnings` | 0 | 806 passed、1 skipped、306 warnings |
| `ruff check app tests alembic scripts __init__.py` | 0 | All checks passed |
| `ruff format --check app tests alembic scripts __init__.py` | 0 | 298 files already formatted |
| `python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed |
| `git diff --check` | 0 | 无空白错误；只有 Git LF/CRLF 提示 |

初次目标测试有 2 项失败：新增缓存前拒绝测试错误地假定测试夹具缓存为空；修正为验证前后缓存状态相同后，全量回归通过。Review 首轮发现未知 schema 类型会被静默跳过，改为显式异常并重跑 pytest、Ruff、格式和基线门禁；第二轮结论为 **pass**，无遗留 blocker、critical、high 或 medium Finding。前端检查和完整 Eval 未运行：Q2 无前端变更，完整 Eval 需要供应商凭据。

Q2 决策：**Accept**；总体目标：**Iterate**。下一轮为 Q3。回滚仅恢复本轮三个源文件、两个测试和对应 6 个精确指纹；不涉及生产外部状态、数据库或 Harness Batch。
