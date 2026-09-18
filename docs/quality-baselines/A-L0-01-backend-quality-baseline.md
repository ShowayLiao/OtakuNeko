# A-L0-01｜后端依赖与质量命令基线

## 结论

本次已把后端质量命令接入真实 `backend/` 路径，并固定了 Python/uv、锁定同步、pytest、Ruff、Mypy 和 deptry 的执行入口。锁文件和运行时质量基线可重复执行，但当前类型检查与依赖合法性检查仍为红项，不能宣称后端质量门禁全部通过。

当前决策：**Accept baseline / Iterate quality debt**。保留失败退出码和证据，下一步单独处理 Mypy 与 deptry 的仓库问题；不在本任务中通过放宽规则、忽略错误或删除依赖制造通过结果。CI 已接入不使用 `continue-on-error` 的基线 job，因此在债务清零前该 job 会按真实退出码失败。

## 真实路径与固定配置

- Python：`backend/.python-version` 固定为 `3.11`。
- uv：`backend/pyproject.toml` 的 `tool.uv.required-version` 固定为 `==0.10.10`；CI 的 `astral-sh/setup-uv` 同时显式指定 `version: "0.10.10"` 和 `python-version: "3.11"`。
- 依赖：`backend/pyproject.toml` 的 `dev` group 新增 `mypy`、`deptry`；`backend/uv.lock` 已重新生成并锁定 108 个解析包。
- 测试：`backend/pyproject.toml` 的 pytest 配置仍以 `tests/` 为入口。
- 类型检查：Mypy 作用域为 `app/harness`、`app/capabilities`、`app/memory`、`app/trace`，启用显式包基准、未类型化函数体检查、隐式 Optional 检查、无效 ignore/冗余 cast 检查及错误码输出。
- CI：`.github/workflows/ci.yml` 的 `software`、`backend-quality-baseline`、`harness`、`benchmark` 四个后端 job 均运行在 `backend/`，并使用 `uv sync --locked --dev` 与 `uv run --locked`；基线 job 真实运行 Mypy 与 deptry，失败不被隐藏。

## 工具版本

以下版本来自锁定 uv 环境，而不是系统全局命令：

| 项目 | 版本 | 证据 |
| --- | --- | --- |
| Python | 3.11.15 | `uv run --locked --directory backend python --version` |
| uv | 0.10.10 | `uv --version`；项目 required-version 和 CI 均固定 |
| pytest | 9.0.3 | `uv run --locked --directory backend pytest --version` |
| Ruff | 0.15.12 | `uv run --locked --directory backend ruff --version` |
| Mypy | 2.3.1 | `uv run --locked --directory backend mypy --version` |
| deptry | 0.25.1 | `uv run --locked --directory backend deptry --version` |

## 命令与退出码

命令均从仓库根目录执行；本机因默认用户 uv cache 无写权限，实际本地复验额外设置了任务缓存目录 `UV_CACHE_DIR=.uv-cache`。CI 使用 Actions runner cache，不依赖该本机目录。成功复验可按以下 PowerShell 片段完整复现：

```powershell
$repo = 'E:\HACCI\Documents\tools\OtakuNeko'
$env:UV_CACHE_DIR = "$repo\.uv-cache"
uv lock --check --directory "$repo\backend"
uv sync --locked --dev --directory "$repo\backend"
uv run --locked --directory "$repo\backend" pytest -q
uv run --locked --directory "$repo\backend" ruff check app tests
uv run --locked --directory "$repo\backend" mypy
uv run --locked --directory "$repo\backend" deptry .
```

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv lock --check --directory backend` | 0 | 锁文件与 `pyproject.toml` 一致，解析 108 个包 |
| `uv sync --locked --dev --directory backend` | 0 | 锁定环境同步成功；uv 提示项目未开启 package entry point 安装，这是已有项目配置事实 |
| `uv run --locked --directory backend pytest -q` | 0 | 746 passed，1 skipped，242 warnings，31.81s |
| `uv run --locked --directory backend ruff check app tests` | 0 | All checks passed |
| `uv run --locked --directory backend mypy` | 1 | 396 errors，涉及 49 个文件，检查 60 个 source files |
| `uv run --locked --directory backend deptry .` | 1 | 发现 12 个 `DEP002` 未使用声明依赖 |
| `uv run --locked --directory backend python -m pip check` | 1 | 不可用：uv 环境未安装 `pip`，输出 `No module named pip` |

### 干净临时环境复验

使用一次性 `UV_PROJECT_ENVIRONMENT` 临时虚拟环境执行 `uv sync --locked --dev`，不复用仓库已有 `.venv`；命令结束后临时目录已删除。联网权限开启后的完整复验结果为：

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv sync --locked --dev --directory backend`（临时环境） | 0 | 安装 102 个环境包，锁定解析 108 个包 |
| `uv run --locked --directory backend python --version`（临时环境） | 0 | Python 3.11.15 |
| `uv run --locked --directory backend pytest -q`（临时环境） | 0 | 746 passed，1 skipped，241 warnings，43.28s |
| `uv run --locked --directory backend ruff check app tests`（临时环境） | 0 | All checks passed |

在另一份一次性临时环境中执行质量债务命令，结果同样可重复但按真实仓库状态失败：

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv sync --locked --dev --directory backend`（临时环境） | 0 | 安装 102 个环境包 |
| `uv run --locked --directory backend mypy`（临时环境） | 1 | 396 errors，49 个文件，60 个 source files |
| `uv run --locked --directory backend deptry .`（临时环境） | 1 | 12 个 dependency issues |

在未授予网络权限的首次隔离复验中，临时环境创建成功，但锁定依赖下载因 socket `os error 10013` 失败，sync 退出 1，后续版本/pytest/Ruff 因环境未安装而退出 1；该临时目录同样已清理。该记录属于环境网络失败，不改变联网后真实复验结果。

### Mypy 失败证据摘要

最终命令使用 `explicit_package_bases = true` 后已越过首次的 `app`/`backend.app` 双模块映射问题，进入真实代码检查。代表性错误包括：

- `app/memory/retrievers/bm25_retriever.py:3`：`rank_bm25` 没有 stubs 或 `py.typed` 标记；
- `app/memory/types.py:170`：`created_at` 类型不匹配；
- `app/harness/contracts.py:37`：`Literal[...]` 参数无效；
- `app/harness/result.py:112`：`str` 没有 `value` 属性；
- `app/memory/interfaces.py:191`：传给 `ContextCompiler.compile` 的 list 类型不兼容。

完整失败总量由命令末尾输出 `Found 396 errors in 49 files (checked 60 source files)` 固定记录；本任务不修改这些业务类型错误。

### deptry 失败证据

deptry 报告以下 12 个依赖在代码库扫描中未被使用（`DEP002`）：

`aiofiles`、`anyio`、`asyncpg`、`certifi`、`click`、`langgraph`、`langgraph-checkpoint-sqlite`、`lxml`、`psycopg2-binary`、`python-dotenv`、`python-multipart`、`uvicorn`。

这些依赖可能由动态导入、部署入口或未被 deptry 静态扫描识别的路径使用；在完成逐项源码核对前，不删除、不加入 ignore 列表。

## 首次失败与环境边界

在未设置任务缓存目录时，以下命令均因 `C:\Users\HACCI\AppData\Local\uv\cache` 无权限而退出 2：`uv lock --check`、锁定同步 dry-run、pytest 和 Ruff。设置仓库内可写的 `UV_CACHE_DIR=.uv-cache` 后，锁检查、同步、pytest 和 Ruff 均能执行并得到上述真实结果。因此该项归类为本机环境失败，不是仓库质量失败。

首次检查还确认：系统 shell Python 为 3.13.5，但项目 uv 环境实际使用 3.11.15；系统 Anaconda 的 `mypy` 曾被 PATH 解析到，但项目环境当时没有 Mypy。此次已将 Mypy 和 deptry 纳入 dev group 并通过 uv lock/sync 安装，后续命令不会依赖全局工具。

## 回归结论与指标

- 通过指标：锁检查 1/1；锁定同步 1/1；Ruff 1/1；pytest 746/746 通过，1 个跳过。
- 失败指标：Mypy 396 个错误；deptry 12 个依赖合法性问题；pip check 不可执行。
- 警告指标：pytest 242 条警告，主要为 Pydantic class-based config 弃用、SQLModel/SQLAlchemy `session.execute()` 弃用，以及本机 `.pytest_cache` 无权限。
- 回归判断：新增依赖和命令没有破坏现有测试与 Ruff；后端 CI 现在使用显式 Python/uv 版本和锁定运行，并真实执行 Mypy/deptry。类型与依赖合法性债务真实存在，基线 job 当前会失败，不能将当前状态判为全质量门禁通过。

## 未运行项目

- 未运行 GitHub Actions 远端 job：当前仅完成本地真实路径验证，没有伪造 CI Run/Eval 编号。
- 未运行前端 lint/typecheck/test/build：不在本任务后端范围内。
- 未运行完整 Agent Eval：本任务只固定依赖和质量命令；benchmark job 的命令已改为 `uv run --locked`，等待实际 CI runner 执行。
- 未执行 `pip check` 的替代修复：uv 环境不带 pip，依赖合法性基线使用 `uv lock --check` + deptry；不为满足命令形式额外安装 pip。

## 下一步

1. 对 396 个 Mypy 错误按模块分组，先解决包边界和第三方类型声明；债务清零前保持当前阻断门禁，之后再按模块收敛规则。
2. 逐项核对 12 个 deptry `DEP002`，区分真实未使用依赖、动态导入、部署入口和工具误报；每个保留项必须有配置或源码依据。
3. 在干净 CI runner 上执行 `software`、`backend-quality-baseline`、`harness` 和 `benchmark` job，补充真实 Run/Eval 链接与远端退出码。
4. 处理 pytest 的 242 条弃用/缓存权限警告，避免警告继续增长。

## 审查结论

共完成 3 轮只读审查：首轮发现 CI 未执行 Mypy/deptry 及成功命令缺少缓存变量，第二轮仅发现一处门禁措辞不一致，均已修复；最终 verdict：**PASS**，无 Critical、Important 或未处理 Minor Finding。

## 回滚

本任务尚未创建 commit。回滚时仅撤销本任务新增或修改的 `backend/pyproject.toml`、`backend/uv.lock`、`.github/workflows/ci.yml`、本报告和对应计划文件；不得覆盖工作区内既有的 `.github/workflows/evaluation.yml`、`.gitignore`、`AGENTS.md`、`README.md`、测试文件及其他用户修改。
