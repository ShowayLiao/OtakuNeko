# A-L0-06｜前端独立质量与全仓库汇总门禁

## 范围与当前实现

基准为 `feature-harness` 普通检出，起点 commit `0562ed48b982ccaea13d85c6cf7dea9c20069f65`；开始时工作区干净。本任务不是 Harness Batch，未创建 Batch execution record。

`.github/workflows/ci.yml` 原有 `software` job 先执行后端 lint、业务层导入边界检查和 pytest，再串行执行前端 lint、typecheck、test、build。现在前端步骤移入独立的 `frontend` job，仍使用 pnpm 10.15.1、Node.js 20.19.0、`frontend/pnpm-lock.yaml` 和原来的五条安装/检查命令。`software` 保留原有后端步骤和名称；`backend-quality-baseline`、`harness`、`benchmark` 的 job 配置未改。

新增 `repository-quality` job 等待上述五个 job。它把各 job 的 `needs.*.result` 写入 GitHub Step Summary，并要求每个结果严格等于 `success`；`failure`、`skipped` 等结果使汇总退出 1。使用 `if: ${{ !cancelled() }}`，使依赖失败后仍可汇总，同时在整个 workflow 被取消时不强制启动汇总。GitHub 文档对依赖失败后的 job 条件和 `!cancelled()` 的用法有明确说明；本地验证不等于远端 Actions Run。

## 失败证据与结构验证

修改前的结构探针找不到独立 `frontend` 和 `repository-quality` job，退出 **1**；修改后相同探针退出 **0**。PyYAML 解析退出 **0**，识别 `software`、`frontend`、`backend-quality-baseline`、`harness`、`benchmark`、`repository-quality` 六个 job。

使用 `git show HEAD:.github/workflows/ci.yml` 与变更后的 YAML 做结构比较，验证三个独立后端 job 完全相同，`software` 的后端步骤逐项相同，原前端步骤按原顺序移入新 job；比较退出 **0**。在本地 Git Bash 中执行从 YAML 读取的汇总脚本：五项 `success` 退出 **0**；模拟 `frontend=failure` 退出 **1**，报 `A required gate did not succeed: failure`；模拟 `benchmark=skipped` 退出 **1**，报 `A required gate did not succeed: skipped`。探针没有修改业务代码或外部状态。

## 本地回归

以下命令在本机使用仓库绝对路径执行，表中以仓库根目录相对写法展示等价命令。PowerShell 的 `pnpm.ps1` 被本机执行策略拦截，普通沙箱中的 `pnpm.cmd` 因上级目录 `EPERM` 退出 1；改用 `pnpm.cmd` 并允许访问工作区路径后，四项实际检查均完成。最初两个环境错误不计为代码失败。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv run --locked --directory backend pytest -q --disable-warnings` | 0 | 800 passed、1 skipped、305 warnings |
| `uv run --locked --directory backend ruff check app tests` | 0 | All checks passed |
| `uv run --locked --directory backend python scripts/check_type_baseline.py` | 0 | 检查 298 个文件；498 条既有错误均在精确基线内 |
| `uv run --locked --directory backend deptry .` | 0 | 扫描 175 个文件，无依赖问题 |
| `uv run --locked --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed、0 failed；报告在 `backend/.runtime/evaluation/fast.json` |
| `pnpm --dir frontend lint` | 0 | 0 error、94 warning |
| `pnpm --dir frontend typecheck` | 0 | `tsc --noEmit` 通过 |
| `pnpm --dir frontend test` | 0 | 13 个文件、96 个测试通过 |
| `pnpm --dir frontend build` | 0 | Next.js 生产构建完成 |

未重跑后端 `TID251`、Harness 专项 pytest/Ruff、格式差异报告步骤：它们的 YAML 配置与起点 commit 完全相同，且后端全量 pytest/Ruff 已运行。未执行远端 GitHub Actions，也未创建 PR、commit 或 push；因此尚无远端 job URL、分支保护规则变更或远端汇总结果。

## 回归结论与下一步

本地结构比较和失败探针支持：前端现在可独立报告失败，汇总脚本在必需 job 失败或跳过时会失败，原后端 job 命令边界未改变。代码回归命令未观察到新增失败。前端 94 条 lint warning 与后端 498 条类型债务仍是当前基线，不能解释为零债务。

下一步是在获得 PR 或 push 授权后检查一次真实 GitHub Actions Run，确认六个 job 及 Step Summary 的远端行为；若仓库使用分支保护，再由有权限者将 `repository-quality` 设为必需检查。回滚只需撤销本任务对 `.github/workflows/ci.yml` 与本报告的改动；无数据库、业务 API、依赖或外部状态变化。
