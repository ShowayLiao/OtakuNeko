# A-L0-02 后端类型与依赖合法性红项修复计划

> **面向 AI 代理的工作者：** 本计划在当前工作区执行；保留既有用户修改，不创建 Batch execution 记录，不提交或推送。

**目标：** 修复 A-L0-01 暴露的 Mypy 396 条错误和 deptry 12 个 `DEP002`，让锁定 CI 基线 job 以退出码 0 完成。

**架构：** 保留 A-L0-01 的 Mypy 检查语义和四个首期架构目录配置，不使用 `follow_imports=skip`、全局 ignore 或 `continue-on-error` 隐藏传递导入错误。类型修复以真实 Optional 收窄、集合/契约签名一致、局部第三方边界 Protocol 或带错误码的窄 ignore 为主；deptry 依赖只在确认未使用后移除，动态导入/部署入口依赖必须补充源码或工具配置依据。

**技术栈：** Python 3.11、uv 0.10.10、Mypy 2.3.1、deptry 0.25.1、pytest、Ruff、FastAPI、Pydantic、SQLModel。

---

### 任务 1：建立可审计的失败分类基线

**文件：**
- 读取：`backend/pyproject.toml`、`backend/uv.lock`、A-L0-01 报告、Mypy 报告涉及的源码文件
- 修改：本计划文件

- [x] **步骤 1：复现当前 Mypy 和 deptry 失败**

运行：

```powershell
$env:UV_CACHE_DIR = "$repo\.uv-cache"
uv run --locked --directory backend mypy --no-pretty
uv run --locked --directory backend deptry .
```

当前证据：Mypy 退出 1，396 errors / 49 files / 60 source files；deptry 退出 1，12 个 `DEP002`。

- [x] **步骤 2：按根因分组而不是按输出顺序修改**

分组包括：Optional/Union 收窄、函数签名覆盖、集合泛型与结构化契约、Pydantic/SQLModel 工厂边界、第三方无 stubs、未使用局部 ignore、异常类型收窄、重复局部变量，以及依赖静态扫描遗漏。

### 任务 2：修复 Mypy 类型错误

**文件：**
- 修改：Mypy 报告涉及的 `backend/app/**/*.py` 文件；仅进行类型正确性修复，不改变业务行为、权限边界、数据库协议或 Harness 控制流。
- 测试：现有相关后端测试由全量 pytest 回归覆盖，不新增仅为迎合 Mypy 的弱断言。

- [x] **步骤 1：修复契约和通用类型根因**

优先处理会产生级联错误的定义：`ActionDescriptor` 的公共构造参数类型、`AgentResult`/`MemoryFact`/`ContextCompiler` 的 list/Sequence 契约、`ModelGateway.synthesize` 参数类型、Harness cancellation/dispatcher 的可信 Optional 边界，以及无效 `Literal` 常量。

- [x] **步骤 2：修复四个首期架构目录中的调用点**

依次处理 `app/harness`、`app/capabilities`、`app/memory`、`app/trace` 的 `arg-type`、`union-attr`、`assignment`、`call-arg`、`return-value` 和 `unused-ignore`。对第三方无 stubs 的导入只允许局部、带错误码且有原因的 ignore；不得添加全局 `ignore_missing_imports`。

- [x] **步骤 3：修复被真实导入链检查到的业务模块类型错误**

处理 `app/schemas`、`app/repositories`、`app/services`、`app/models` 等 Mypy 实际报告文件中的 Pydantic/SQLModel 类型不一致。若修复需要改变运行时数据契约、API 行为或数据库结构，停止并记录为扩展范围，不用类型注解掩盖行为变化。

- [x] **步骤 4：每个错误组完成后运行增量 Mypy 和相关测试**

运行：

```powershell
uv run --locked --directory backend mypy --no-pretty
uv run --locked --directory backend pytest <受影响测试目录> -q
```

预期：错误数量单调下降；若错误数量不降或出现新类别，回到根因分析，不叠加猜测性修复。

### 任务 3：清理 deptry 依赖合法性问题

**文件：**
- 修改：`backend/pyproject.toml`、必要的 `backend/app/**/*.py` 或依赖配置文件
- 生成：如依赖声明发生变化，更新 `backend/uv.lock`

- [x] **步骤 1：逐项核对 12 个 DEP002**

依赖清单：`aiofiles`、`anyio`、`asyncpg`、`certifi`、`click`、`langgraph`、`langgraph-checkpoint-sqlite`、`lxml`、`psycopg2-binary`、`python-dotenv`、`python-multipart`、`uvicorn`。

对每项检查 Python import、动态加载、FastAPI/ASGI 入口、Alembic/部署脚本和 Docker 运行路径；不能只因 deptry 静态扫描不到就删除。

- [x] **步骤 2：移除确认未使用依赖或补充可验证依据**

确认未使用的依赖从 `project.dependencies` 移除并重新锁定；确认由动态导入/部署入口使用的依赖，在 deptry 支持的项目配置中加入最小、可解释的排除或入口声明。禁止 broad ignore、删除实际运行时依赖和新增无依据依赖。

- [x] **步骤 3：复跑 deptry 与锁文件检查**

运行：

```powershell
uv lock --check --directory backend
uv run --locked --directory backend deptry .
```

预期：两个命令退出码均为 0，且依赖变更没有引入 Ruff、pytest 或启动导入回归。

### 任务 4：完整验证、干净环境和报告

**文件：**
- 修改：`docs/quality-baselines/A-L0-02-backend-quality-baseline.md`
- 验证：`.github/workflows/ci.yml` 的 `backend-quality-baseline` job

- [x] **步骤 1：运行本地完整门禁**

```powershell
uv lock --check --directory backend
uv sync --locked --dev --directory backend
uv run --locked --directory backend mypy
uv run --locked --directory backend deptry .
uv run --locked --directory backend ruff check app tests
uv run --locked --directory backend pytest -q
```

- [x] **步骤 2：使用一次性环境复验可重复性**

通过 `UV_PROJECT_ENVIRONMENT` 指向系统临时目录，执行锁定同步、Mypy、deptry、Ruff 和 pytest；记录每条命令的退出码。验证结束后只删除本次创建的临时目录。

- [x] **步骤 3：审查 CI 门禁和完整差异**

确认 workflow 没有 `continue-on-error`、全局 ignore 或条件跳过；运行 `git diff --check`、`git diff --stat`、路径引用检查，并审查完整未提交 diff，保留既有用户修改。

- [x] **步骤 4：编写报告并交接**

报告记录修复前后错误数量、删除/保留依赖及依据、版本、命令退出码、测试统计、警告、CI Run/Eval（如未运行则明确说明）、遗留风险、下一步和回滚方式。不创建 commit 或 PR。
