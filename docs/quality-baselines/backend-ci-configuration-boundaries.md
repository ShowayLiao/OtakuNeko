# 后端与 CI 配置边界及验证结果

更新：2026-10-10。状态：实现、本地验证与最终只读审查完成，Review verdict 为 pass。
分支：feature-harness；验证基线 HEAD：2289ddc77d2ae1d0c1838b87ba3f6e9f2f3b9384。初始工作区干净、普通检出。未创建 Harness Batch 执行记录；验证结束时尚未提交或推送。

## 覆盖清单与权威检查

统一 CI 命令（仓库根目录）：

~~~text
uv run --locked --directory backend python scripts/check_configuration_coverage.py --probe-tools
uv run --locked --directory backend pytest tests/test_configuration.py tests/test_configuration_coverage.py -q
~~~

统一入口实际执行应用离线加载器、actionlint 与 Docker Compose；捕获真实退出码，不用“解析成功”代替所有配置语义。报告路径为 backend/.runtime/quality/configuration-coverage.json；CI 上传为 configuration-coverage artifact。

表中 A 为 uv run --locked --directory backend python scripts/check_configuration.py。该脚本从真实加载器或类型定义校验，不连接数据库、不实例化生产 target/Judge。

| 配置文件 | 实际消费者 | 权威检查及覆盖边界 |
| --- | --- | --- |
| backend/pyproject.toml | uv、pytest、Ruff、Mypy、deptry | 已有 uv sync --locked --dev、deptry、lint/typecheck/format/test 阻断；A 增加 TOML 解析 |
| backend/uv.lock | uv、backend/Dockerfile | 已有 uv sync --locked --dev；A 增加 TOML 解析；Docker 的 --frozen 不等同于 --locked |
| .github/workflows/ci.yml | GitHub Actions | actionlint -shellcheck= -pyflakes= .github/workflows/ci.yml .github/workflows/evaluation.yml |
| .github/workflows/evaluation.yml | GitHub Actions | 同上；检查工作流 Schema/表达式，不包含 shellcheck、pyflakes，也不证明运行环境与外部 Actions 可用 |
| docker-compose.yml | Docker Compose | docker compose --env-file .env.example -f docker-compose.yml config --quiet；只校验配置模型，不构建或启动容器 |
| backend/alembic.ini | Alembic Config/ScriptDirectory、alembic/env.py 的日志配置 | A：Alembic 配置及脚本目录、SQLAlchemy URL、日志组/引用/标准 handler 类、args/kwargs 签名、level、formatter、propagate；不执行迁移或动态日志插件 |
| .env.example | 根工作目录下 Settings 的 .env 模板、Compose 插值模板 | A：dotenv.parser 语法、缺值、重复/未知键、Settings.model_fields 与真实字段类型 |
| backend/.env.example | backend 工作目录下 Settings 的 .env 模板 | 同上；模板不会自动作为 .env 加载 |
| backend/evals/config/fast.yaml | EvaluationConfig/load_config、runner | A：真实 Schema、有限阈值、实际聚合指标、dataset/baseline 引用与版本、非空标签选择、factory 顶层符号；原 fast Eval 阻断保留 |
| backend/evals/config/observability.yaml | 同上 | A：相同离线检查；既有定时/手动 observability Eval 保留 |
| backend/evals/config/full.yaml | 同上、production target/Judge | A：相同离线检查、factory AST 检查；不调用 Provider、不产生付费 Judge 请求；既有 full Eval 保留 |
| backend/evals/baselines/v1-fast.json | app.evaluation.judge.load_baseline | A：真实 Baseline Schema、有限数值；对应 YAML 校验 dataset_version 和指标可用性 |
| backend/evals/baselines/v1-full.json | 同上 | 同上 |
| backend/typecheck-baseline.json | scripts/check_type_baseline.py | A：checked_files 与 errors 字段/非负整数契约；既有 uv run --locked python scripts/check_type_baseline.py 检查完整 Mypy 结果 |

初始清单共 14 个配置文件，6 个缺少独立合法性检查（两个工作流、Compose、INI、两个环境模板）。最终报告：configuration_count=14、covered_count=14、failed_count=0、uncovered_count=0。

覆盖分母由 git ls-files 发现 backend 内 TOML/INI/lock/YAML/JSON/环境模板，加两个工作流及根环境模板/Compose；同时扫描工作流目录与 Eval 配置目录中新出现的 YAML。新发现但未登记、缺少结果、未知状态、重复结果、工具缺失或任何校验失败均返回非零。covered 表示已有校验结果，不表示每个路径都验证了生产部署行为。

## CI 阻断与工具依据

.github/workflows/ci.yml 新增 configuration job：锁定安装后端依赖，安装 SHA-256 校验后的 actionlint 1.7.12，记录工具版本，执行统一校验及工具错误探针、配置回归测试，always 上传覆盖报告。

repository-quality 的 needs、结果环境变量、结果表和非 success 返回 1 的循环均包含 configuration。无 continue-on-error；configuration 失败或跳过会导致汇总失败。仓库分支保护的远程设置未读取/修改，因此这里只宣称工作流汇总阻断，不能宣称已配置远程 required status check。

actionlint 使用现有 GitHub Actions 文件作为项目依据，命令见 [官方用法](https://github.com/rhysd/actionlint/blob/main/docs/usage.md)。Linux amd64 归档 SHA-256 为 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8；本地 Windows amd64 归档 SHA-256 为 6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9，均核对官方 1.7.12 checksums。Compose config --quiet 的依据见 [官方命令文档](https://github.com/docker/compose/blob/main/docs/reference/compose_config.md)。未新增项目依赖或修改锁文件。

Python 3.11 使用标准库 tomllib；3.10 缺少该模块时使用既有 uv 的原生命令 uv lock --check --offline --no-cache --no-python-downloads --python <当前解释器> --directory <backend>，对 pyproject/lock 联合校验且不写锁文件。此分支已通过模拟 tomllib 不存在的真实 uv 回归；未运行完整 Python 3.10 测试环境。

## 环境与引用边界

- Settings 检查清除业务环境变量，并在空临时工作目录中加载；保留 Windows SystemRoot 等必要 OS 环境。未知键先按真实 Settings 字段拒绝，避免 extra=ignore 掩盖拼写错误。异常仅输出路径与安全分类，不输出值或 raw ValidationError。
- 源码直接 getenv 的额外键为 OPENAI_BASE_URL、INTERACTIVE_RUN_STORE_ENABLED、HARNESS_COORDINATOR_ENABLED、MEMORY_TRUST_MODE、OTAKUNEKO_MCP_USER_ID；模板允许它们，布尔/正整数键有类型检查。不改变 Runtime 或业务配置语义。
- Eval 引用的三个数据集为 backend/evals/datasets/v1.jsonl、v1-full.jsonl、v1-observability.jsonl；由真实 load_dataset 校验，作为 YAML 引用路径而不重复计入 14 个配置文件。引用限制在 backend 范围，factory 查找仅检查模块顶层函数，不为解析 factory 导入指定模块或调用函数；Baseline Schema 的正常导入仍复用 judge 模块。
- 真实 .env、backend/.env、部署环境值及凭据不纳入模板门禁，不读取或写入报告。完整 full Eval 和生产迁移未运行；这些动态路径不能被“清单内未覆盖 0”代替。
- 前端 package.json、pnpm-lock.yaml、pnpm-workspace.yaml、eslint.config.mjs、tsconfig.json、vitest.config.ts、next.config.ts、postcss.config.mjs、tailwind.config.js 由原 frontend job 消费；本次未重新执行前端门禁，也未做前端专项配置审计。
- 根 package.json/pnpm-lock.yaml、.codex 工具配置、业务样本 JSON、缓存与生成文件不计入后端配置分母。
- Dockerfile 是构建配方：backend/Dockerfile 未做构建验证；Compose 声明 frontend build: ./frontend，但 git ls-files 没有 frontend/Dockerfile。两条构建路径单独排除，不将 Compose 配置通过写成镜像可构建或系统可部署。

## 真实验证及退出码

本地从仓库根目录执行；uv 命令设置 UV_CACHE_DIR=E:/HACCI/Documents/tools/OtakuNeko/.uv-cache、DEBUG=false，使用 --offline。下表为实现及修复后的最终验证；未触发远程 CI，远程 job 退出码为 UNKNOWN。

| 完整命令 | 退出码 | 结果 |
| --- | --- | --- |
| uv run --locked --offline --directory backend pytest -q --disable-warnings | 0 | 846 passed、0 failed、1 skipped、310 warnings；warnings 明细由参数隐藏，未逐条整改 |
| uv run --locked --offline --directory backend pytest tests/test_configuration.py tests/test_configuration_coverage.py -q | 0 | 40 passed、0 failed、0 skipped、1 PytestCacheWarning（缓存目录权限） |
| uv run --locked --offline --directory backend ruff check app tests alembic scripts __init__.py | 0 | 全范围 lint 通过 |
| uv run --locked --offline --directory backend ruff format --check app tests alembic scripts __init__.py | 0 | 302 个文件已符合格式 |
| uv run --locked --offline --directory backend python scripts/check_type_baseline.py | 0 | 检查 302 个文件、0 错误，许可 0 |
| uv run --locked --offline --directory backend deptry . --no-ansi | 0 | 扫描 177 个文件、0 依赖问题 |
| uv run --locked --offline --directory backend ruff check --select TID251 app/services app/models app/repositories app/schemas | 0 | 业务 import 边界通过 |
| uv lock --check --offline --directory backend | 0 | 105 packages，锁文件未改动；命令选项由 uv lock --help 核对 |
| uv run --locked --offline --directory backend python scripts/check_configuration_coverage.py --actionlint "E:/HACCI/Documents/tools/OtakuNeko/backend/.runtime/quality/actionlint.exe" --compose "C:/Program Files/Docker/Docker/resources/cli-plugins/docker-compose.exe" --probe-tools | 0 | 14/14；application=0、actionlint=0、compose=0、negative_probes=0 |
| backend/.runtime/quality/actionlint.exe -shellcheck= -pyflakes= .github/workflows/ci.yml .github/workflows/evaluation.yml | 0 | 实际工作流合法性通过 |
| "C:/Program Files/Docker/Docker/resources/cli-plugins/docker-compose.exe" --env-file .env.example -f docker-compose.yml config --quiet | 0 | Compose 2.40.3-desktop.1 配置通过；Docker 用户配置访问权限警告、Compose version 属性过时警告 |

最初普通 Shell helper 启动失败，常规检查通过 Node child_process 执行；actionlint 下载通过已自动批准的网络权限执行，随后验证归档哈希。普通 docker compose 因用户配置权限/插件发现不可用，退出 125；改用已有插件完成真实检查，不把环境故障算作错误配置探针。

修复前出现过真实失败：新增覆盖测试缺少实现（退出 2）；应用临时副本测试发现日志引用/环境加载缺口（退出 1）；Mypy 新增 5 条类型问题（退出 1）；模拟无 tomllib 返回 NameError（退出 1）；日志 kwargs/propagate 探针被错误接受（退出 1）；空 tags 探针被错误接受（退出 1，1 failed/1 passed），修复后为 2 passed。均修复并重新运行相关检查；没有降低断言或修改已发布 fixture。

## 错误探针和汇总退出码

| 探针 | 实际退出码/结论 |
| --- | --- |
| 非法工作流 runs-of 键 | actionlint 返回 1；统一入口要求探针恰为 1，工具缺失 127 不算成功拒绝 |
| Compose 非法字段 invalid_configuration_field | Compose 返回 1；同样区分工具/超时故障 |
| 临时配置副本中的未知/重复/缺值/错误类型环境变量，非法 YAML 字段、缺失 dataset/baseline、空 tags、未知/非有限阈值、非法 factory、日志引用/类/级别/kwargs/propagate、非法 TOML、基线 Schema/版本、类型债务字段 | 真正配置 CLI 返回 1；由 tests/test_configuration.py 断言，并确认 probe-secret 不出现在报告或输出 |
| 新增未登记配置、缺失/未知/重复结果、非零工具退出码、缺失工具 | 覆盖测试断言返回失败，未覆盖与失败计数分开 |
| 从 ci.yml 提取原样汇总 Bash：所有结果 success | Git Bash 实际执行返回 0 |
| 同一汇总 Bash：configuration=failure 或 skipped，其余 success | 分别返回 1 |

所有错误配置测试仅操作 pytest 临时副本；真实 .env.example 和 fast.yaml 已恢复初始内容及行尾。统一入口的工具探针位于 OS TemporaryDirectory，并在结束时清理；早期手动工具探针、下载与覆盖报告位于忽略的 backend/.runtime/quality/，没有进入 diff。

文档检查：git diff --check、git diff --stat、rg -n "standard-agent-harness-reference|harness-execution|BATCH-[0-9]+" AGENTS.md docs 均退出 0；rg 命中 518 行。Git diff/stat 只覆盖已跟踪文件，新增文件另行完整读取审查，六个新增文件执行 git diff --no-index --check -- NUL <文件>，均退出 1（存在新增文件差异），无空白错误诊断；Git 全局 ignore 权限及 LF/CRLF 提示保留为环境警告。

## 交付与回滚

变更文件：.github/workflows/ci.yml、backend/scripts/check_configuration.py、backend/scripts/check_configuration_coverage.py、backend/tests/test_configuration.py、backend/tests/test_configuration_coverage.py、本清单、backend-ci-configuration-plan.md。没有业务代码、数据库、依赖或锁文件变更。

审查结论：pass；完整七文件只读审查，无未处理 Finding。Python 3.10 兼容、空 tags 与探针路径说明问题已修复并复验；Reviewer 读取源码和覆盖 JSON，命令结果取自协调者实际执行记录，未重复执行测试。未解决范围限制：远程 CI/分支保护、完整 3.10 环境、动态部署值、构建/迁移/付费 Eval 没有验证；静态 Schema 通过不证明这些能力。

回滚：在 .github/workflows/ci.yml 删除此次 configuration job 及对应 needs/环境变量/表行/循环项，删除此次新增脚本、测试和两个文档即可；保留原有软件、前端、Harness、benchmark 门禁。没有迁移或外部状态需要补偿。

## 最终 Review 记录

~~~yaml
review_result:
  batch: null
  kind: documentation
  verdict: pass
  summary: 七个任务文件完整审查通过；14/14 配置有真实检查结果，未覆盖 0，错误探针与 CI 汇总失败路径均已验证。
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
    - command: uv run --locked --offline --directory backend pytest tests/test_configuration.py tests/test_configuration_coverage.py -q
      exit_code: 0
    - command: uv run --locked --offline --directory backend ruff check app tests alembic scripts __init__.py
      exit_code: 0
    - command: uv run --locked --offline --directory backend ruff format --check app tests alembic scripts __init__.py
      exit_code: 0
    - command: uv run --locked --offline --directory backend python scripts/check_type_baseline.py
      exit_code: 0
    - command: uv run --locked --offline --directory backend deptry . --no-ansi
      exit_code: 0
    - command: uv run --locked --offline --directory backend ruff check --select TID251 app/services app/models app/repositories app/schemas
      exit_code: 0
    - command: 'uv run --locked --offline --directory backend python scripts/check_configuration_coverage.py --actionlint "E:/HACCI/Documents/tools/OtakuNeko/backend/.runtime/quality/actionlint.exe" --compose "C:/Program Files/Docker/Docker/resources/cli-plugins/docker-compose.exe" --probe-tools'
      exit_code: 0
    - command: git diff --check
      exit_code: 0
  reviewed_files:
    - .github/workflows/ci.yml
    - backend/scripts/check_configuration.py
    - backend/scripts/check_configuration_coverage.py
    - backend/tests/test_configuration.py
    - backend/tests/test_configuration_coverage.py
    - docs/quality-baselines/backend-ci-configuration-boundaries.md
    - docs/quality-baselines/backend-ci-configuration-plan.md
  deferred_findings: []
~~~
