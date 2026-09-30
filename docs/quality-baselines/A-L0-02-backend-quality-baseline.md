# A-L0-02｜后端类型与依赖合法性红项修复

## 结论

A-L0-01 暴露的后端质量债务已清零：Mypy 从 396 个错误降至 0，deptry 从 12 个 `DEP002` 降至 0。锁定环境、本地全量回归和一次性临时环境均通过；`backend-quality-baseline` 的两个真实阻断命令具备通过条件。

当前决策：**Accept / 进入下一项能力迭代**。本地已验证 CI job 的等价命令，但本次没有运行 GitHub Actions 远端 Run，因此不能伪造远端 CI Run/Eval 编号。

## 修复范围

### Mypy

- 修复 Harness、Capabilities、Memory、Trace 四个首期架构目录中的 Optional/Union 收窄、结构化契约、`Sequence` 参数、枚举/Literal、异常类型和取消/调度边界。
- 修复真实导入链涉及的 Pydantic/SQLModel、Repository、Service 和 SQL 表达式类型；SQLModel 类属性只在查询表达式边界使用局部 `cast(Any, ...)`，没有改动数据库字段或查询语义。
- `rank_bm25` 仅保留带错误码和原因的局部 `# type: ignore[import-untyped]`，没有增加全局 `ignore_missing_imports`、`follow_imports=skip` 或全局忽略。
- 保持既有测试行为；发现一次 mock 合约回归后移除无必要的运行时 subject 判定，仅保留原有查询调用。

### deptry / 依赖声明

| 处理 | 依赖 | 依据 |
| --- | --- | --- |
| 从运行时直接依赖移除 | `aiofiles`、`anyio`、`certifi`、`click`、`psycopg2-binary`、`python-multipart` | 未发现后端源码或部署入口的直接使用；必要时仍由其他包作为传递依赖安装 |
| 从运行时依赖移动到 `dev` | `langgraph`、`langgraph-checkpoint-sqlite` | 测试直接导入 `backend/tests/memory/test_*.py`；`backend/app/memory/manager.py:13` 的 `AsyncSqliteSaver` 为 `TYPE_CHECKING` 边界 |
| 保留并使用最小逐包例外 | `asyncpg`、`lxml`、`python-dotenv`、`uvicorn` | `backend/alembic.ini:87` 和 `backend/app/core/config.py:66` 使用 PostgreSQL async URL；`backend/app/services/bangumi_service.py:652,690` 指定 `lxml`；`backend/app/core/config.py:71` 使用 `.env` 加载；`backend/Dockerfile:20` 以 `uvicorn app.main:app` 启动 |

保留项只配置为：

```toml
[tool.deptry]
per_rule_ignores = { DEP002 = ["asyncpg", "lxml", "python-dotenv", "uvicorn"] }
```

这是 4 个已核对边界依赖的逐包 `DEP002` 例外，不是 broad ignore；未使用的 8 个直接声明已移除或移至开发依赖。

## 版本与锁文件

- Python：3.11（`backend/.python-version`）。
- uv：0.10.10（`backend/pyproject.toml` 和 CI 均固定）。
- 锁定环境解析：`backend/uv.lock`，`uv lock --check` 报告 105 个解析包。
- 锁定环境工具：Mypy 2.3.1、deptry 0.25.1、Ruff 0.15.12、pytest 9.0.3。

## 本地真实命令与退出码

命令均以仓库根目录为起点，使用 `UV_CACHE_DIR=.uv-cache` 解决本机 uv cache 写权限边界；CI runner 不依赖该本地目录。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv lock --check --directory backend` | 0 | 锁文件与项目声明一致 |
| `uv sync --locked --dev --directory backend` | 0 | 锁定开发环境同步成功 |
| `uv run --locked --directory backend mypy` | 0 | `Success: no issues found in 60 source files` |
| `uv run --locked --directory backend deptry .` | 0 | 扫描 174 个文件，`Success! No dependency issues found.` |
| `uv run --locked --directory backend ruff check app tests` | 0 | `All checks passed!` |
| `uv run --locked --directory backend pytest` | 0 | 746 passed，1 skipped，242 warnings |
| `git diff --check` | 0 | 无新增 whitespace 错误 |

## 一次性干净环境复验

使用新的 `UV_PROJECT_ENVIRONMENT` 临时目录执行 `uv sync --locked --dev`，未复用仓库 `.venv`；验证完成后已删除该临时目录。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv sync --locked --dev --directory backend` | 0 | 干净环境安装 99 个包 |
| `uv run --locked --directory backend mypy` | 0 | 60 个源文件无错误 |
| `uv run --locked --directory backend deptry .` | 0 | 无依赖问题 |
| `uv run --locked --directory backend ruff check app tests` | 0 | 全部通过 |
| `uv run --locked --directory backend pytest` | 0 | 746 passed，1 skipped，242 warnings |
| 组合门禁 | 0 | 4 条质量/测试命令全部通过 |

## CI 门禁核对

`.github/workflows/ci.yml` 的 `backend-quality-baseline` 仍然在 `backend/` 工作目录中执行：

```bash
set +e
uv run --locked mypy
mypy_exit=$?
uv run --locked deptry .
deptry_exit=$?
set -e
echo "mypy exit code: $mypy_exit"
echo "deptry exit code: $deptry_exit"
test "$mypy_exit" -eq 0 && test "$deptry_exit" -eq 0
```

该 job 没有 `continue-on-error`、条件跳过、全局类型忽略或删除检查；两个命令均为 0 时才通过。已用同一锁定环境在本地复现其真实命令，未运行远端 GitHub Actions。

## 回归结论、遗留风险与下一步

- 回归结论：Mypy、deptry、Ruff、pytest 和锁定同步均通过；类型修复未引入新的测试失败。pytest 仍有 242 条已有警告，主要是 Pydantic class-based config 和 SQLModel/SQLAlchemy `session.execute()` 弃用提示。
- 遗留风险：`asyncpg`、`lxml`、`python-dotenv`、`uvicorn` 的 deptry 例外依赖部署或配置边界，未来若入口或配置移除，应同步删除例外；SQLite checkpoint 仍只保证单 Worker，未在本任务扩展共享 recovery。
- 下一步：在有权限的 GitHub runner 上触发并记录 `backend-quality-baseline` 真实 Run；随后单独处理已有弃用警告和共享 checkpoint/worker recovery 风险。

## Artifacts

- PR/Commit：未创建，等待用户明确授权。
- Run/Eval：本地锁定环境和一次性环境复验已完成；GitHub Actions 远端 Run 未执行。
- Report：本文件。

## 回滚

本任务未创建 commit。回滚时仅撤销本任务对应的后端类型修复、`backend/pyproject.toml`、`backend/uv.lock`、本报告和计划文件；不得覆盖工作区中 A-L0-01 或其他用户已有修改。
