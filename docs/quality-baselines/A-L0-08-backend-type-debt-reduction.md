# A-L0-08｜后端类型债务收紧

## 范围与基线

本次从 `feature-harness` 的 `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe` 开始，工作区原本干净。没有活动 Harness Batch；本记录是普通质量改进报告，不是 Batch 执行记录。Mypy 扫描范围保持 `app tests alembic scripts __init__.py`，精确指纹门禁仍由 `backend/scripts/check_type_baseline.py` 执行；没有修改 Mypy 配置或 CI 命令。

## 逐轮结果

| 轮次 | 处理范围 | Mypy 错误数 | 报错文件数 | 受检文件数 | 清单许可数 | 回归与结论 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 初始 | 既有全量基线 | 498 | 74 | 298 | 498 | 门禁退出 0，债务与许可清单一致 |
| 第 1 轮 | Alembic `AutoString` 导入与清理脚本 SQL 表达式 | 494 | 72 | 298 | 494 | 删除 4 条已消失的指纹；门禁退出 0；Ruff lint 通过 |
| 第 2 轮 | `test_subject_repo_write_paths.py` 的模型夹具与可空 ID | 426 | 71 | 298 | 426 | 再删除 68 条已消失的指纹；9 个定向测试通过；全量回归通过 |
| 第 3 轮 | `test_metrics.py` 的评估模型夹具 | 406 | 70 | 298 | 406 | 再删除 20 条已消失的指纹；6 个定向测试与 Ruff 检查通过 |
| 第 4 轮 | `test_collection_repo_write_paths.py` 的部分更新夹具与可空 ID | 369 | 69 | 298 | 369 | 再删除 37 条已消失的指纹；8 个定向测试与全量回归通过 |

迁移只把 `AutoString` 改为直接导入，生成的 SQLAlchemy 列定义未变。清理脚本用 `sqlmodel.col()` 表达原有的空字符串与 `NULL` 条件，保留相同的 SQL 谓词。仓储测试补齐模型入参和非空 ID 断言；部分字段夹具使用 `model_validate()`，保留 Pydantic 运行时校验及 `exclude_unset` 所需的字段集合。缺少 `name` 或 `type` 的 upsert 测试仍由仓储层验证并抛出 `ValueError`。评估指标测试的动态覆盖值也改用 `model_validate()` 验证，事件夹具通过 `ScriptEvent` 校验。

## 最终验证

以下命令使用锁定的离线 uv 环境；本机将 `UV_CACHE_DIR` 设为仓库内 `.uv-cache`。全量及仓储定向 pytest 设置 `DEBUG=false`、`DEPLOY_MODE=local`；门禁单元测试设置 `DEBUG=false`。退出码来自本次实际运行。

| 命令（从仓库根目录表示） | 退出码 | 结果 |
| --- | ---: | --- |
| `uv run --locked --offline --directory backend python scripts/check_type_baseline.py` | 0 | 298 个文件，369 条错误，清单许可 369 条 |
| `uv run --locked --offline --directory backend mypy --no-pretty app tests alembic scripts __init__.py` | 1 | 369 条现存错误，69 个报错文件，检查 298 个文件；原生命令按预期非零 |
| `uv run --locked --offline --directory backend pytest tests/test_type_baseline.py -q --disable-warnings` | 0 | 2 passed；覆盖新增错误、同一指纹次数增加和扫描文件数下降时失败的比较逻辑 |
| `uv run --locked --offline --directory backend pytest tests/repositories/test_subject_repo_write_paths.py -q` | 0 | 9 passed，36 warnings |
| `uv run --locked --offline --directory backend pytest tests/test_type_baseline.py tests/evaluation/test_metrics.py tests/repositories/test_collection_repo_write_paths.py -q --disable-warnings` | 0 | 16 passed，28 warnings |
| `uv run --locked --offline --directory backend pytest -q --disable-warnings` | 0 | 800 passed，1 skipped，306 warnings |
| `uv run --locked --offline --directory backend ruff check app tests alembic scripts __init__.py` | 0 | `All checks passed!` |
| `uv run --locked --offline --directory backend ruff format --check app tests alembic scripts __init__.py` | 0 | 298 个文件符合格式 |
| `uv run --locked --offline --directory backend deptry . --no-ansi` | 0 | 扫描 175 个文件，无依赖问题 |

未运行前端 lint、typecheck、test、build 或 Agent Eval：没有修改前端、接口协议或 Harness 行为。未运行远端 CI：没有 push 或创建 PR 的授权。原生 Mypy 仍有 369 条债务，不能宣称后端类型检查已零错误。现有 `compare_baseline` 测试验证新增错误及覆盖收缩仍会失败；本次没有放宽比较规则。

## 审查与回滚

完整未提交 diff 限于迁移、清理脚本、三个测试文件、`backend/typecheck-baseline.json` 和本报告。清单只删除实际消失的 129 条许可，未增加忽略项或改变扫描范围。对照源码与测试，未发现未处理的 blocker、critical、high 或 medium Finding；本地 Review verdict 为 **pass**。回滚本次七个文件的改动即可恢复初始状态；执行前须保留之后产生的用户修改，不能重置整个工作区。
