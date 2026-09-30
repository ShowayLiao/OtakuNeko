# Code Quality CI Gates 实现计划

> **面向 AI 代理的执行说明：** 使用 `executing-plans` 按任务顺序实施本计划。开始前必须进入干净的隔离 worktree；不得覆盖当前工作区中的用户修改。所有提交步骤都需要用户另行明确授权，禁止自行 push。

**目标：** 为 OtakuNeko 建立可重复、可阻断、无外部服务依赖的 `format-check`、`lint`、`typecheck` 和 `project-sanity` CI 门禁，同时保持现有软件测试、Harness 回归和 Agent evaluation 的职责不变。

**架构：** 质量检查按运行时分成 `backend-quality`、`frontend-quality` 和 `repository-sanity` 三个并行 job，最后由只汇总状态的 `quality-gate` 作为分支保护入口。格式化基线与规则加严分开实施；后端类型检查先覆盖契约敏感的 Harness、Capability、Memory 和 Trace 边界，再单独规划全后端扩面。

**技术栈：** GitHub Actions、uv、Ruff、Mypy、pnpm、Prettier、ESLint、TypeScript、Next.js `typegen`、Alembic、pytest、actionlint、Docker Compose。

---

## 1. 范围、事实和停止条件

### 当前源码事实

- 基线分支为 `feature-harness`，计划编写时 HEAD 为 `ebbeae0d4f9941667e295494e6b82691849b72ea`。
- 当前工作区已有未提交的 `.github/workflows/evaluation.yml`、`README.md`、`backend/tests/acceptance/test_primary_runtime_decision_loop.py`，以及未跟踪的 CI 设计、计划和 `.github/workflows/ci.yml`；这些内容不属于本计划编写产生的修改。
- 后端已有 Ruff，`ruff check app tests` 当前通过；没有 Ruff 项目配置和 Mypy 依赖。
- `ruff format --check app tests` 当前报告 214 个文件需要格式化、67 个文件已符合格式。
- 前端已有 Next.js ESLint、`strict` TypeScript 和 `tsc --noEmit`；没有 Prettier。
- 根目录与 `frontend/` 各有一套 `package.json` 和 `pnpm-lock.yaml`。根依赖与前端依赖重复，当前 CI 草案只验证 `frontend/pnpm-lock.yaml`。
- `frontend/dockerfile` 的文件名大小写不符合 Linux 默认查找的 `Dockerfile`，并且镜像中使用 `pnpm@latest`；`docker-compose.yml` 仍包含已废弃的 `version` 字段。
- 后端声明 `requires-python = ">=3.10"`，开发版本文件为 `backend/.python-version` 的 Python 3.11。

### 包含范围

- Python 和前端源码的确定性格式契约。
- Ruff、ESLint 和无效 lint-disable 的阻断策略。
- 前端完整类型生成与 TypeScript 检查。
- 后端关键架构边界的 Mypy 检查。
- 锁文件、工具版本、GitHub Actions、应用导入、Alembic 迁移图、架构边界和 Docker Compose 配置检查。
- 将质量 job 接入现有 CI 草案，并提供一个稳定的 `quality-gate` 分支保护名称。

### 不包含范围

- 不修改 Harness Runtime、Decision、Dispatcher、Capability 或业务行为。
- 不修改 evaluation 数据集、阈值、baseline 或 live-provider 流程。
- 不把依赖漏洞、许可证、Secret scanning 混入 code-quality job；它们应使用独立 security workflow。
- 本计划不完成 Mypy 对 `backend/app` 全目录的 strict 覆盖；首期只覆盖 `app/harness`、`app/capabilities`、`app/memory` 和 `app/trace`。
- 不执行生产部署、生产数据库迁移或真实外部 API 调用。

### 执行停止条件

- 当前 CI 草案及其关联修改尚未提交或无法明确归属时，不得直接开始实现；先由用户决定将其纳入隔离 worktree、提交或保留在当前工作区。
- 格式化命令修改了允许范围以外的文件，立即停止并恢复该命令产生的文件；不得覆盖用户原有修改。
- Ruff/Mypy 加严需要改变公共 API 或业务语义才能通过时，停止并拆出独立修复计划。
- 后端关键目录的 Mypy 错误无法通过局部类型收窄解决时，不得使用全局 `ignore_errors`、无错误码的 `type: ignore` 或删除注解制造通过结果。
- Docker 或 Alembic 验证需要连接生产资源时，立即停止，改用 CI 临时 SQLite 和只读配置检查。

## 2. 预期文件边界

### 创建

- `.editorconfig`：编辑器级字符集、缩进、换行和末尾换行契约。
- `.gitattributes`：Git 文本文件换行契约；不执行全仓库无差别 renormalize。
- `frontend/.prettierrc.json`：前端与仓库配置文件的 Prettier 规则。
- `frontend/.prettierignore`：排除依赖、构建输出、锁文件、日志、运行数据和二进制资源。
- `backend/tests/architecture/test_migration_graph.py`：Alembic 单一 head 不变量。
- `backend/tests/smoke/test_application_import.py`：FastAPI 应用导入 smoke test。

### 修改

- `package.json`：删除重复运行时依赖，保留仓库命令入口并声明 `pnpm@10.15.1`。
- `frontend/package.json`：增加 Prettier、格式脚本、严格 ESLint 参数、`next typegen` 和 Node engine。
- `frontend/pnpm-lock.yaml`：锁定新增的 Prettier 依赖。
- `frontend/next.config.ts`：删除“父目录存在第二份 lockfile”的过期说明，保留明确的前端 Turbopack root。
- `backend/pyproject.toml`：增加 Ruff/Mypy 配置和 Mypy 开发依赖。
- `backend/uv.lock`：锁定 Mypy 及其依赖。
- `.github/workflows/ci.yml`：接入三个质量 job 和汇总 gate，移除已有 job 中重复的 lint/typecheck 步骤。
- `docker-compose.yml`：删除废弃的顶层 `version` 字段。
- `frontend/dockerfile` → `frontend/Dockerfile`：修正大小写并固定 pnpm 版本。

### 机械格式化范围

- `backend/app/**/*.py`
- `backend/tests/**/*.py`
- `backend/alembic/**/*.py`
- `backend/scripts/**/*.py`
- `frontend/src/**/*.{ts,tsx,js,jsx,css,json}`
- `frontend/*.{ts,js,mjs,json}`
- `.github/workflows/*.{yml,yaml}`
- 根目录 `package.json`

格式化任务不得修改上述范围以外的业务文件、评估 fixture、数据库文件或生成报告。

## 3. 任务分解

### 任务 1：Preflight 和隔离工作区

**文件：** 无修改。

- [ ] **步骤 1：记录 Git 基线**

  ```powershell
  git status --short
  git branch --show-current
  git rev-parse HEAD
  git worktree list --porcelain
  ```

  预期：能够逐项归属所有已有修改；若仍与本计划开头记录一致，也必须先获得用户对隔离方式的确认。

- [ ] **步骤 2：建立或选择隔离 worktree**

  使用 `using-git-worktrees` 技能。隔离 worktree 必须基于已经包含待扩展 CI 草案的明确 commit；不得通过复制未提交文件绕过来源确认。

- [ ] **步骤 3：重新读取实施依据**

  ```powershell
  git status --short
  Get-Content -Raw AGENTS.md
  Get-Content -Raw docs/code-review.md
  Get-Content -Raw docs/superpowers/specs/2026-09-02-ci-verification-pipeline-design.md
  Get-Content -Raw docs/superpowers/plans/2026-09-02-ci-verification-pipeline.md
  ```

  预期：隔离 worktree 干净，且没有被自动解释为活动 Harness Batch。

### 任务 2：收敛 Node/pnpm 和容器工具链契约

**文件：**

- 修改：`package.json`
- 删除：`pnpm-lock.yaml`
- 修改：`frontend/package.json`
- 修改：`frontend/next.config.ts`
- 重命名并修改：`frontend/dockerfile` → `frontend/Dockerfile`
- 修改：`docker-compose.yml`

- [ ] **步骤 1：确认重复依赖事实**

  ```powershell
  Get-Content -Raw package.json
  Get-Content -Raw frontend/package.json
  Get-Content -TotalCount 40 pnpm-lock.yaml
  Get-Content -TotalCount 40 frontend/pnpm-lock.yaml
  ```

  预期：根目录仅重复持有 `emoji-picker-react` 和 `zustand`，实际 Next.js 应用依赖由 `frontend/package.json` 管理。

- [ ] **步骤 2：把根 package 收敛为命令入口**

  将根 `package.json` 调整为：

  ```json
  {
    "private": true,
    "packageManager": "pnpm@10.15.1",
    "scripts": {
      "dev": "pnpm --dir frontend dev",
      "build": "pnpm --dir frontend build",
      "start": "pnpm --dir frontend start",
      "format:check": "pnpm --dir frontend format:check",
      "lint": "pnpm --dir frontend lint",
      "typecheck": "pnpm --dir frontend typecheck",
      "test": "pnpm --dir frontend test"
    }
  }
  ```

  删除根 `pnpm-lock.yaml`。根 package 不再拥有依赖，因此不得重新生成空的第二份 lockfile。

- [ ] **步骤 3：声明前端运行时版本**

  在 `frontend/package.json` 保留 `packageManager: "pnpm@10.15.1"`，并增加：

  ```json
  "engines": {
    "node": ">=20.9.0"
  }
  ```

  该下限与仓库安装的 Next.js 16 engine 契约一致；CI 继续固定 Node 20.19.0。

- [ ] **步骤 4：修正前端 Dockerfile 契约**

  使用两步 Git 重命名，保证 Windows 大小写不敏感文件系统也能正确记录：

  ```powershell
  git mv frontend/dockerfile frontend/Dockerfile.rename-tmp
  git mv frontend/Dockerfile.rename-tmp frontend/Dockerfile
  ```

  将：

  ```dockerfile
  RUN corepack enable && corepack prepare pnpm@latest --activate
  ```

  改为：

  ```dockerfile
  RUN corepack enable && corepack prepare pnpm@10.15.1 --activate
  ```

  `COPY package.json pnpm-lock.yaml ./` 保持使用 `frontend/` 内唯一应用 lockfile。

- [ ] **步骤 5：清理已知配置 warning**

  删除 `docker-compose.yml` 的：

  ```yaml
  version: "3.8"
  ```

  在 `frontend/next.config.ts` 中删除第二份 lockfile 的过期说明；保留：

  ```ts
  turbopack: {
    root: path.resolve(__dirname),
  },
  ```

- [ ] **步骤 6：验证依赖和 Compose 配置**

  ```powershell
  pnpm --dir frontend install --frozen-lockfile
  docker compose config --quiet
  git status --short
  ```

  预期：两个命令退出码均为 0；根 `pnpm-lock.yaml` 已删除；Compose 不再报告 `version` 字段废弃。

- [ ] **可选提交点，仅在用户授权后**

  ```powershell
  git add package.json pnpm-lock.yaml frontend/package.json frontend/next.config.ts frontend/dockerfile frontend/Dockerfile docker-compose.yml
  git commit -m "build: align project package and container tooling"
  ```

### 任务 3：建立格式化契约

**文件：**

- 创建：`.editorconfig`
- 创建：`.gitattributes`
- 创建：`frontend/.prettierrc.json`
- 创建：`frontend/.prettierignore`
- 修改：`frontend/package.json`
- 修改：`frontend/pnpm-lock.yaml`
- 修改：`backend/pyproject.toml`

- [ ] **步骤 1：添加跨编辑器文本契约**

  `.editorconfig` 使用以下内容：

  ```ini
  root = true

  [*]
  charset = utf-8
  end_of_line = lf
  insert_final_newline = true
  trim_trailing_whitespace = true

  [*.{py,js,jsx,ts,tsx,json,yml,yaml,md,toml}]
  indent_style = space
  indent_size = 2

  [*.py]
  indent_size = 4

  [*.md]
  trim_trailing_whitespace = false
  ```

  `.gitattributes` 使用以下内容，不运行 `git add --renormalize .`：

  ```gitattributes
  * text=auto
  *.py text eol=lf
  *.js text eol=lf
  *.jsx text eol=lf
  *.ts text eol=lf
  *.tsx text eol=lf
  *.json text eol=lf
  *.toml text eol=lf
  *.yml text eol=lf
  *.yaml text eol=lf
  *.md text eol=lf
  *.sh text eol=lf
  *.bat text eol=crlf
  *.cmd text eol=crlf
  ```

- [ ] **步骤 2：配置 Ruff formatter**

  在 `backend/pyproject.toml` 增加：

  ```toml
  [tool.ruff]
  target-version = "py310"
  line-length = 88

  [tool.ruff.format]
  quote-style = "double"
  indent-style = "space"
  line-ending = "lf"
  ```

- [ ] **步骤 3：安装和配置 Prettier**

  ```powershell
  pnpm --dir frontend add --save-dev --save-exact prettier
  ```

  `frontend/.prettierrc.json`：

  ```json
  {
    "semi": true,
    "singleQuote": false,
    "trailingComma": "all",
    "printWidth": 100,
    "endOfLine": "lf"
  }
  ```

  `frontend/.prettierignore`：

  ```text
  .next/
  node_modules/
  public/
  store/
  *.log
  *.md
  pnpm-lock.yaml
  tsconfig.tsbuildinfo
  ```

  在 `frontend/package.json` 增加：

  ```json
  "format": "prettier --write . ../.github/workflows ../package.json",
  "format:check": "prettier --check . ../.github/workflows ../package.json"
  ```

- [ ] **步骤 4：证明格式门禁在旧基线上会失败**

  ```powershell
  uv run --directory backend ruff format --check app tests alembic scripts
  pnpm --dir frontend format:check
  ```

  预期：至少 Ruff 命令退出非零，并列出既有格式债务；不得在这一小步降低规则或扩大 ignore。

### 任务 4：建立一次性格式化基线

**文件：** 仅修改第 2 节列出的机械格式化范围。

- [ ] **步骤 1：运行格式化写入命令**

  ```powershell
  uv run --directory backend ruff format app tests alembic scripts
  pnpm --dir frontend format
  ```

- [ ] **步骤 2：立即验证 formatter 幂等**

  ```powershell
  uv run --directory backend ruff format --check app tests alembic scripts
  pnpm --dir frontend format:check
  ```

  预期：两个命令退出码均为 0，再次运行不产生新 diff。

- [ ] **步骤 3：检查格式化范围和语义回归**

  ```powershell
  git status --short
  git diff --check
  git diff --stat
  uv run --directory backend pytest
  pnpm --dir frontend typecheck
  pnpm --dir frontend test
  pnpm --dir frontend build
  ```

  预期：测试、类型检查和 build 全部退出 0；没有 evaluation fixture、依赖配置、数据库或运行报告被 formatter 意外修改。

- [ ] **步骤 4：逐文件审查完整格式化 diff**

  ```powershell
  git diff -- backend/app backend/tests backend/alembic backend/scripts frontend/src frontend/*.ts frontend/*.js frontend/*.mjs frontend/*.json .github/workflows package.json
  ```

  确认修改只涉及空白、换行、引号、逗号、括号布局和 import 排版，没有更改字面值、条件、调用顺序或断言。

- [ ] **可选提交点，仅在用户授权后**

  显式暂存任务 3 的配置文件和任务 4 实际被 formatter 修改的文件；禁止使用 `git add .` 或 `git add -A`。

### 任务 5：加严 Ruff 和 ESLint

**文件：**

- 修改：`backend/pyproject.toml`
- 修改：`frontend/package.json`
- 修改：Ruff/ESLint 报告命中的允许范围源码文件

- [ ] **步骤 1：配置 Ruff lint 规则**

  在 `backend/pyproject.toml` 增加：

  ```toml
  [tool.ruff.lint]
  select = ["E4", "E7", "E9", "F", "I", "UP", "B", "ASYNC", "RUF"]

  [tool.ruff.lint.per-file-ignores]
  "tests/**/*.py" = ["B011"]
  "alembic/versions/*.py" = ["E501"]
  ```

  不启用与 formatter 冲突的格式规则，不使用全局 `ignore` 隐藏新规则的全部报告。

- [ ] **步骤 2：预览 Ruff 自动修复**

  ```powershell
  uv run --directory backend ruff check app tests alembic scripts --fix --diff
  ```

  审查预览后，才运行：

  ```powershell
  uv run --directory backend ruff check app tests alembic scripts --fix
  ```

  剩余问题逐项人工修复。禁止使用 `--unsafe-fixes`。

- [ ] **步骤 3：把 ESLint warning 和无效禁用声明设为失败**

  将前端脚本调整为：

  ```json
  "lint": "eslint . --max-warnings=0 --report-unused-disable-directives"
  ```

  删除无效 `eslint-disable`；确需保留的禁用必须限定到最小文件或行范围，并保留解释。

- [ ] **步骤 4：验证 lint 和格式仍通过**

  ```powershell
  uv run --directory backend ruff check app tests alembic scripts
  uv run --directory backend ruff format --check app tests alembic scripts
  pnpm --dir frontend lint
  pnpm --dir frontend format:check
  ```

  预期：四个命令退出码均为 0，ESLint 为零 warning。

### 任务 6：完善前端类型检查入口

**文件：**

- 修改：`frontend/package.json`
- 修改：TypeScript 报告命中的 `frontend/src/**/*.ts` 和 `frontend/src/**/*.tsx`

- [ ] **步骤 1：让类型检查不依赖历史 `.next` 输出**

  将脚本改为：

  ```json
  "typecheck": "next typegen && tsc --noEmit"
  ```

- [ ] **步骤 2：从干净生成目录运行类型检查**

  将当前 `frontend/.next` 移到工作区外的临时目录或在全新 worktree 中执行；不要删除用户目录。然后运行：

  ```powershell
  pnpm --dir frontend typecheck
  ```

  预期：`next typegen` 生成路由、页面和布局类型，`tsc --noEmit` 退出 0。

- [ ] **步骤 3：验证生成物没有进入 Git diff**

  ```powershell
  git status --short
  git ls-files frontend/.next frontend/tsconfig.tsbuildinfo
  ```

  预期：`.next` 和 `tsconfig.tsbuildinfo` 均未被跟踪。

### 任务 7：引入后端关键边界 Mypy gate

**文件：**

- 修改：`backend/pyproject.toml`
- 修改：`backend/uv.lock`
- 修改：`backend/app/harness/**/*.py`
- 修改：`backend/app/capabilities/**/*.py`
- 修改：`backend/app/memory/**/*.py`
- 修改：`backend/app/trace/**/*.py`

- [ ] **步骤 1：添加 Mypy 开发依赖**

  ```powershell
  uv add --directory backend --dev mypy
  ```

- [ ] **步骤 2：配置首期检查边界**

  在 `backend/pyproject.toml` 增加：

  ```toml
  [tool.mypy]
  python_version = "3.10"
  plugins = ["pydantic.mypy"]
  files = ["app/harness", "app/capabilities", "app/memory", "app/trace"]
  check_untyped_defs = true
  no_implicit_optional = true
  warn_unused_ignores = true
  warn_redundant_casts = true
  show_error_codes = true
  pretty = true
  ```

- [ ] **步骤 3：运行首个类型基线**

  ```powershell
  uv run --directory backend mypy
  ```

  对报告执行以下固定策略：

  - 缺失返回类型：补充真实返回类型，不使用 `Any` 作为默认逃生口。
  - 可空值问题：在可信边界显式检查 `None`，不使用无条件 `cast`。
  - 第三方库类型不完整：优先添加窄 Protocol 或带错误码的局部 `type: ignore[code]`，并写明库边界原因。
  - SQLAlchemy/SQLModel 工厂签名：保留现有带错误码的局部 ignore，只有在 Mypy 证明不再需要时才删除。
  - 需要修改四个允许目录之外的生产代码时停止，把该错误及导入链记录为扩面前置项。

- [ ] **步骤 4：验证 Mypy 与现有检查共存**

  ```powershell
  uv run --directory backend mypy
  uv run --directory backend ruff check app tests alembic scripts
  uv run --directory backend ruff format --check app tests alembic scripts
  uv run --directory backend pytest tests/harness tests/acceptance tests/capabilities tests/trace -q
  ```

  预期：四个命令退出码均为 0。全 `backend/app` 扩面作为后续独立任务记录，不在此处放宽首期 gate。

### 任务 8：添加项目健全性测试

**文件：**

- 创建：`backend/tests/architecture/test_migration_graph.py`
- 创建：`backend/tests/smoke/test_application_import.py`

- [ ] **步骤 1：添加 Alembic 单一 head 断言**

  `backend/tests/architecture/test_migration_graph.py`：

  ```python
  from pathlib import Path

  from alembic.config import Config
  from alembic.script import ScriptDirectory


  BACKEND_ROOT = Path(__file__).resolve().parents[2]


  def test_alembic_has_exactly_one_head() -> None:
      config = Config(str(BACKEND_ROOT / "alembic.ini"))
      script = ScriptDirectory.from_config(config)

      assert len(script.get_heads()) == 1, script.get_heads()
  ```

- [ ] **步骤 2：添加应用导入 smoke test**

  `backend/tests/smoke/test_application_import.py`：

  ```python
  from fastapi import FastAPI

  from app.main import app


  def test_fastapi_application_imports() -> None:
      assert isinstance(app, FastAPI)
  ```

- [ ] **步骤 3：运行新增检查和既有架构守卫**

  ```powershell
  uv run --directory backend pytest tests/architecture/test_migration_graph.py tests/smoke/test_application_import.py -q
  uv run --directory backend pytest tests/architecture tests/capabilities/test_architecture.py -q
  ```

  预期：新增测试通过；既有 API/Service、Agent/Service、Capability/API 和 Harness/API 依赖方向守卫继续通过。

- [ ] **步骤 4：验证临时 SQLite 迁移链**

  在 CI job 中设置：

  ```yaml
  env:
    DEPLOY_MODE: local
    SQLITE_FILE: ${{ runner.temp }}/otakuneko-migration-check.db
  ```

  然后运行：

  ```powershell
  uv run --directory backend alembic upgrade head
  uv run --directory backend alembic check
  ```

  预期：只创建 runner 临时数据库，两个命令退出码均为 0，不连接 PostgreSQL 或其他外部资源。

### 任务 9：将质量门禁接入 GitHub Actions

**文件：**

- 修改：`.github/workflows/ci.yml`

- [ ] **步骤 1：增加 `backend-quality` job**

  复用当前 uv setup 和 `uv sync --locked --dev`，依次执行：

  ```text
  uv run ruff format --check app tests alembic scripts
  uv run ruff check app tests alembic scripts
  uv run mypy
  uv run pytest tests/architecture tests/smoke tests/capabilities/test_architecture.py -q
  uv run alembic upgrade head
  uv run alembic check
  ```

  Alembic 步骤使用任务 8 定义的 runner 临时 SQLite 环境变量。

- [ ] **步骤 2：增加 `frontend-quality` job**

  固定 Node 20.19.0、pnpm 10.15.1，使用 `frontend/pnpm-lock.yaml`，依次执行：

  ```text
  pnpm install --frozen-lockfile
  pnpm format:check
  pnpm lint
  pnpm typecheck
  ```

  不使用 `npx` 动态下载未锁定工具，不使用 `continue-on-error`。

- [ ] **步骤 3：增加 `repository-sanity` job**

  使用 `actions/setup-go@v5` 并设置 `go-version: "1.24.x"`，固定执行：

  ```text
  go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
  docker compose config --quiet
  ```

  另加 Bash 断言：根 `pnpm-lock.yaml` 不存在，`frontend/Dockerfile` 使用准确大小写存在，`frontend/package.json` 与 `frontend/pnpm-lock.yaml` 同时存在。

- [ ] **步骤 4：增加稳定汇总 gate**

  新增：

  ```yaml
  quality-gate:
    name: quality-gate
    if: ${{ always() }}
    needs: [backend-quality, frontend-quality, repository-sanity]
    runs-on: ubuntu-latest
    steps:
      - name: Require all quality jobs
        shell: bash
        run: |
          test "${{ needs.backend-quality.result }}" = "success"
          test "${{ needs.frontend-quality.result }}" = "success"
          test "${{ needs.repository-sanity.result }}" = "success"
  ```

  分支保护只需稳定要求 `quality-gate`；三个实际 job 仍可独立显示失败原因。

- [ ] **步骤 5：消除现有 job 中的重复职责**

  - `software` 保留后端完整 pytest、前端 Vitest 和 Next.js build。
  - 从 `software` 删除已迁移到 quality jobs 的 Ruff、ESLint 和 TypeScript 步骤。
  - `harness` 保留确定性回归测试，删除已由 `backend-quality` 全范围覆盖的重复 Ruff 步骤。
  - `benchmark` 保持 offline fast evaluation 和 artifact 上传不变。
  - `evaluation.yml` 保持定时/手动 observability 与 full evaluation 边界不变。

- [ ] **步骤 6：静态审查 Workflow**

  ```powershell
  go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
  rg -n "continue-on-error|OPENAI_API_KEY|pnpm@latest|uv:latest|pnpm-lock.yaml|quality-gate|ruff format|mypy|actionlint|alembic check" .github/workflows backend/Dockerfile frontend/Dockerfile
  ```

  预期：`ci.yml` 无 secret/live provider、无错误吞掉逻辑；`OPENAI_API_KEY` 只存在于受限的定时/手动 full evaluation job。`uv:latest` 若仍存在于后端运行镜像，应记录到独立的容器供应链加固任务，不在本计划中顺手修改。

### 任务 10：完整验证、Review 和交接

**文件：** 无新增实现文件；只验证任务 2—9 的修改。

- [ ] **步骤 1：运行全部 code-quality gate**

  ```powershell
  uv run --directory backend ruff format --check app tests alembic scripts
  uv run --directory backend ruff check app tests alembic scripts
  uv run --directory backend mypy
  pnpm --dir frontend format:check
  pnpm --dir frontend lint
  pnpm --dir frontend typecheck
  go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
  docker compose config --quiet
  ```

- [ ] **步骤 2：运行项目规定的完整回归**

  ```powershell
  uv run --directory backend pytest
  pnpm --dir frontend test
  pnpm --dir frontend build
  uv run --directory backend pytest tests/harness tests/acceptance tests/capabilities tests/trace -q
  uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml
  ```

  每条命令记录退出码、通过/失败/跳过数量和 warning。任何未运行项必须记录原因，不得写成通过。

- [ ] **步骤 3：检查迁移和临时资源边界**

  在临时 SQLite 配置下执行：

  ```powershell
  uv run --directory backend alembic upgrade head
  uv run --directory backend alembic check
  ```

  确认临时数据库位于 runner temp 或明确的任务临时目录，没有生成仓库内 `.db`、日志或 evaluation report diff。

- [ ] **步骤 4：执行完整 diff 自审**

  ```powershell
  git status --short
  git diff --check
  git diff --stat
  git diff
  ```

  对照第 2 节文件边界，确认没有业务行为、公共 API、evaluation 契约、Secret、数据库内容或未授权用户修改被改变。

- [ ] **步骤 5：按 `docs/code-review.md` 独立 Review**

  Review 阶段只报告 finding，不修改。若存在 medium 及以上 finding，退出 Review，修复后重新运行任务 10 的全部适用命令，再重新审查完整 diff。合格 verdict 必须为 `pass`，且 blocker/critical/high/medium finding 全部清零。

- [ ] **步骤 6：交接**

  交接必须列出：

  - changed files；
  - 四类质量门禁的命令和退出码；
  - 后端/前端测试和 build 结果；
  - Harness 与 fast evaluation 结果；
  - Review verdict 和轮数；
  - Mypy 首期覆盖边界及尚未覆盖的后端目录；
  - 回滚方式：按获授权的独立提交逆序回滚，不运行生产迁移；
  - 分支保护下一步：将 `quality-gate` 设置为 required check。

## 4. 验收标准

- `format-check`：Ruff 和 Prettier 在干净 checkout 上均退出 0，重复执行不产生 diff。
- `lint`：Ruff 覆盖 `app/tests/alembic/scripts`；ESLint 零 warning，未使用的 disable 声明会失败。
- `typecheck`：前端先执行 Next.js type generation 再执行 strict `tsc`；后端 Mypy 覆盖四个关键架构目录。
- `project-sanity`：actionlint、锁文件策略、准确大小写的 Dockerfile、Compose 配置、应用导入、单 Alembic head、临时数据库 upgrade/check 和既有依赖方向测试全部通过。
- CI 的 `software`、`harness`、`benchmark` 和定时/手动 `evaluation` 职责没有被质量重构改变。
- PR 必需门禁使用稳定的 `quality-gate` 名称；任一子 job 被取消、跳过或失败时，汇总 gate 不得成功。
- 工作区不存在意外生成文件、Secret、数据库、缓存、日志或完整 provider payload。

## 5. 后续独立任务

以下项目不阻塞首期质量 gate，但必须单独规划，不能在实施时顺手扩大范围：

1. 将 Mypy 从四个关键架构目录扩展到整个 `backend/app`，再评估测试目录类型检查。
2. 使用 `deptry` 和 `knip` 建立未使用/缺失依赖检查。
3. 为后端运行镜像固定 uv 镜像 digest，并为 GitHub Actions 建立 SHA pinning 策略。
4. 建立独立的 Secret、依赖漏洞和许可证 security workflow。
5. 根据 CI 时长数据决定是否增加 Python 3.10/3.11 兼容矩阵；在此之前 Ruff 和 Mypy 均按声明的最低 Python 3.10 解析代码。
