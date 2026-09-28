# A-L0-03｜后端 lint 与依赖合法性门禁

## 结果与范围

`.github/workflows/ci.yml` 的 `software` job 在 `backend/` 运行 `ruff check app tests`，覆盖生产代码和测试代码；`backend-quality-baseline` job 运行 `deptry .`，检查后端项目依赖声明。两个现有步骤均阻断 CI。本次新增同在 `software` job 的 Ruff `TID251` 步骤，检查 `app/services`、`app/models`、`app/repositories`、`app/schemas`，禁止这些业务层目录直接导入 `langgraph`、`langchain_core`、`langchain_openai`、`openai`。规则写在 `backend/pyproject.toml`，命中时输出文件、行列和 `TID251`。

框架适配层、API 入口和测试不在 `TID251` 限制范围内。deptry 的默认扫描排除 `tests`，用于判断生产依赖是否被使用；测试文件由 Ruff 覆盖。试将 `tests` 纳入 deptry 扫描会把合法的 `pytest`、`langgraph` 开发依赖报为 `DEP004`，因此保留工具默认边界。规则检查静态 import，不覆盖动态加载；该限制适用于 Ruff 和 deptry。

## 本地验证

在 `feature-harness`、`b7ebedf2a76311cec6f33861ad6315ab3a6ce8ac` 的普通检出执行；开始时 `git status --short` 为空。以下命令均以仓库根目录为起点。未执行远端 GitHub Actions Run，也未运行 Agent Eval，因为本次只修改静态质量门禁。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv lock --check --directory backend` | 0 | 锁文件一致，解析 105 个包 |
| `uv run --locked --directory backend ruff check app tests` | 0 | 全范围 lint 通过 |
| `uv run --locked --directory backend ruff check --select TID251 app/services app/models app/repositories app/schemas` | 0 | 业务层禁止导入检查通过 |
| `uv run --locked --directory backend deptry . --no-ansi` | 0 | 扫描 174 个文件，0 个依赖问题 |
| `uv run --locked --directory backend mypy` | 0 | 60 个源文件无问题 |
| `uv run --locked --directory backend pytest -q` | 0 | 798 passed、1 skipped、305 warnings |

pytest 警告主要来自已有的 Pydantic class config 和 SQLModel/SQLAlchemy `session.execute()` 弃用提示；本次不修改业务代码处理这些警告。

## 失败定位证据

以下探针使用 Ruff 标准输入或 `backend/.runtime/quality/` 下的一次性 deptry 项目，未修改被检查的生产与测试源文件。

| 探针 | 退出码 | 实际定位 |
| --- | ---: | --- |
| `import os` 输入至 `ruff check --stdin-filename tests/_a_l0_03_probe.py -` | 1 | `tests/_a_l0_03_probe.py:1:8`，`F401` 未使用 import |
| `from langgraph.graph import StateGraph` 输入至 `ruff check --select TID251 --stdin-filename app/services/_a_l0_03_probe.py -` | 1 | `app/services/_a_l0_03_probe.py:1:1`，`TID251` 禁止 `langgraph` |
| `from openai import AsyncOpenAI` 输入至相同的 `TID251` 命令 | 1 | `app/services/_a_l0_03_probe.py:1:1`，`TID251` 禁止 `openai` |
| `from langchain_core.tools import tool` 与 `from langchain_openai import ChatOpenAI` 输入至相同的 `TID251` 命令 | 1 | `app/services/_a_l0_03_probe.py:1:1`、`:2:1`，两条 `TID251` |
| 一次性 `pyproject.toml` 声明未使用的 `httpx>=0.26`，执行 `uv run --locked deptry --no-ansi --config <探针 pyproject.toml> <探针目录>` | 1 | `<探针目录>/pyproject.toml: DEP002 'httpx' defined as a dependency but not used in the codebase` |

deptry 的 `DEP002` 是项目声明层面的问题，定位到 `pyproject.toml`，没有源码行号。Ruff 的导入违规均有行列。探针目录在仓库忽略的 `.runtime/quality/` 下；其第一次写入带 BOM 导致 TOML 解析失败，改为无 BOM 后得到上表的规则失败，该环境错误不计入门禁结果。

## 结论与下一步

本地锁定环境中，新增门禁和既有 lint、依赖、类型及测试回归均退出 0；三类违规探针均按预期退出 1 并给出文件与规则。结论：**Accept 本地门禁 / 等待远端 CI Run 验证**。后续在获得 PR 或 push 授权后检查 GitHub Actions 的 `software` 与 `backend-quality-baseline` 真实 Run；若业务层增加新的目录，应明确决定是否纳入 `TID251` 路径列表。没有远端 Run/Eval 编号。

完整变更审查结论：**pass**；改动限于 CI、Ruff 配置和本报告，未发现阻断或待处理的中高风险问题。`git diff --check` 退出 0；CI YAML 解析退出 0，确认 `software` job 含 lint 与禁止导入两个步骤。没有活动 Harness Batch，因此不创建 Batch 执行记录。

回滚仅需撤销本任务对 `.github/workflows/ci.yml`、`backend/pyproject.toml` 和本报告的改动；本次无数据库、运行时 API 或外部状态变更。PR 与远端 CI Run 尚未创建；本地提交状态以 Git 历史为准。
