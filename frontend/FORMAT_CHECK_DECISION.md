# Frontend 格式检查接入决定与验证

日期：2026-10-13。决定：**接入现有 frontend job 的阻塞式 `format:check`**。本地回归、独立审查及新 SHA 的远端 CI 验证均已完成；本任务验收通过。

## 范围与债务

初始测量基线：`e124dc7866ba43deef7500054a5ecc6972637840`。前端 110 个可格式化跟踪文件中有 104 个格式债务文件（94.5%）。固定 Prettier 3.6.2、默认 80 列时预计 `+9,139/-5,895` 行；120 列仍涉及 104 个文件，预计 `+6,589/-6,140` 行。初次因此暂缓门禁，随后用户要求清债并明确批准接入。

清债已提交为 `3a52d15c7437addcbb92dd2a5000bbbc85fb1ec4`，这也是本轮接入基线，开始时工作区干净。清债实际 diff 为 104 个文件、`+9,104/-5,882` 行；债务由 104 降至 0。另有一个 YAML checkout 换行差异，LF 规范化后没有 Git 内容 diff。`fetcher.test.ts` 第一轮链式调用排版非幂等，第二轮格式化后稳定，语法结构与字面值保持相同。

本轮只修改 6 个文件：

| 文件                                | 职责                                                  |
| ----------------------------------- | ----------------------------------------------------- |
| `frontend/package.json`             | 增加 `format:check`，固定开发依赖 Prettier 3.6.2      |
| `frontend/pnpm-lock.yaml`           | 仅新增 Prettier 的 importer、package 与 snapshot 记录 |
| `frontend/.prettierrc.json`         | 固定 80 列和 LF，其他规则使用固定版本默认值           |
| `frontend/.prettierignore`          | 排除生成的 `pnpm-lock.yaml`                           |
| `.github/workflows/ci.yml`          | 仅在 frontend 安装后、lint 前增加格式步骤             |
| `frontend/FORMAT_CHECK_DECISION.md` | 记录范围、债务、验证和远端状态                        |

门禁覆盖前端的 TS/TSX/JS/MJS/CJS/CSS/JSON/Markdown/YAML/YML。当前实际匹配 **112 个文件**：111 个既有跟踪文件（含清债记录），加新增 `.prettierrc.json`；格式债务为 **0**。生成的 lockfile 与不属于此格式范围的静态资源不计入债务。

复用前端 `.gitignore`、仓库 `.gitignore` 和 `.prettierignore`，排除依赖、构建产物、环境文件和本地忽略的诊断产物。没有忽略既有源码或失败测试。glob 有引号，由 Prettier 跨平台展开；未来新增匹配扩展名的文件也受检查。

workflow 的逐字比较确认：移除新增 4 行 frontend 步骤后，与基线相同。未更改其他 jobs、聚合依赖、CI 触发条件、权限或业务代码。`repository-quality` 继续汇总已有 frontend job，因此格式不合规会通过 frontend 失败传递到聚合结果，没有新增独立 job。

## 实施计划与状态

使用 writing-plans 技能将计划保存在本产物中；没有创建 Harness Batch 或手工任务日志。

- [x] 固定工具、格式规则、检查范围与忽略规则，增加前端脚本。
- [x] 仅向现有 frontend job 添加格式步骤。
- [x] 核对 frozen-lockfile 安装、格式正反探针和四项前端回归。
- [x] 核对工作流配置门禁与配置失败回归。
- [x] 完成最终独立审查：1 轮，verdict 为 pass，findings 为空；六个变更文件均符合范围。
- [x] 变更已提交并推送到现有 PR #8，接入 commit 为 `31677268e0e684f90329fd2ee63ac2c4c3f69c31`。
- [x] 核验同一新 SHA 的 frontend 和 repository-quality；两者及全部 7 个 CI jobs 均为 success。

## 本地验证

固定依赖安装命令：`pnpm dlx pnpm@10.15.1 --dir frontend add --save-dev --save-exact prettier@3.6.2 --ignore-scripts`，退出码 0，lockfile 没有无关包变化。

| 完整命令或验证                                                                                                                                                                                                         | 退出码 | 结果                                                                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -----: | -------------------------------------------------------------------------------------- |
| 接入前 `pnpm --dir frontend format:check`                                                                                                                                                                              |      1 | 缺少脚本，红灯基线                                                                     |
| `pnpm dlx pnpm@10.15.1 --dir frontend install --frozen-lockfile`                                                                                                                                                       |      0 | lockfile 一致，安装通过                                                                |
| `pnpm --dir frontend format:check`                                                                                                                                                                                     |      0 | 全部匹配文件合规                                                                       |
| 临时不合规 `src/format-check-ci-probe.ts` + `pnpm --dir frontend format:check`                                                                                                                                         |      1 | 报告该文件，证明门禁能拒绝格式差异                                                     |
| 临时不合规 `.next/format-check-ci-probe.ts` + 同一检查                                                                                                                                                                 |      0 | 生成文件正确忽略                                                                       |
| 探针移除后 `pnpm --dir frontend format:check`                                                                                                                                                                          |      0 | 回到干净状态；临时文件均在 finally 中移除                                              |
| `pnpm --dir frontend format:check --log-level debug` 的路径覆盖核对                                                                                                                                                    |      0 | 111 个既有范围内跟踪文件全部覆盖，新配置也覆盖，合计 112                               |
| `pnpm --dir frontend lint`                                                                                                                                                                                             |      0 | 0 错误、94 个既有警告                                                                  |
| `pnpm --dir frontend typecheck`                                                                                                                                                                                        |      0 | 通过                                                                                   |
| `pnpm --dir frontend test`                                                                                                                                                                                             |      0 | 14 个文件、99 个测试通过；失败 0、跳过 0                                               |
| `pnpm --dir frontend build`                                                                                                                                                                                            |      0 | 生产构建通过                                                                           |
| actionlint 1.7.12：`actionlint -shellcheck= -pyflakes= .github/workflows/ci.yml .github/workflows/evaluation.yml`                                                                                                      |      0 | 两个 workflow 校验通过                                                                 |
| `uv run --locked --directory backend python scripts/check_configuration_coverage.py --probe-tools --actionlint C:/Users/HACCI/AppData/Local/Temp/otakuneko-actionlint-5c0606369350432fb27f845c0b419ba7/actionlint.exe` |      0 | 14 项配置，失败 0、未覆盖 0；application/actionlint/compose/negative_probes 全部退出 0 |
| `uv run --locked --directory backend pytest tests/test_configuration.py tests/test_configuration_coverage.py -q`                                                                                                       |      0 | 40 个测试通过；失败 0、跳过 0                                                          |

本机 actionlint 从官方 1.7.12 Windows release 下载到系统临时目录，校验官方 checksum 后运行。实际路径为 `C:/Users/HACCI/AppData/Local/Temp/otakuneko-actionlint-5c0606369350432fb27f845c0b419ba7/actionlint.exe`；上述配置覆盖命令的路径参数实际使用此值。

本地 Node.js 为 24.12.0；四项前端回归使用宿主 pnpm 11.0.9，依赖与 frozen-lockfile 安装使用 CI 指定 pnpm 10.15.1。CI 固定 Node.js 20.19.0、pnpm 10.15.1 的远端结果已核验为 success。既有警告包括 94 个 lint 警告、安装时 `@emoji-mart/react` 的 React 19 peer 兼容警告及 Git LF/CRLF checkout 提示，均未纳入本次格式任务。

未运行完整后端、Harness/Eval 或浏览器视觉检查：没有后端源码、运行行为、UI 外观或交互变更；仅针对 workflow 运行现有配置门禁与回归。

## CI 结果与提交边界

2026-10-13 只读查询 GitHub API，确认本地 HEAD 与 [PR #8](https://github.com/ShowayLiao/OtakuNeko/pull/8) 的 head 一致：`31677268e0e684f90329fd2ee63ac2c4c3f69c31`。接入 commit 为 `3167726`，清债 commit 为 `3a52d15`，两者均已在该 PR 中。

对应新 SHA 的 [CI run 38378018557](https://github.com/ShowayLiao/OtakuNeko/actions/runs/38378018557) 已完成，conclusion 为 **success**，触发事件为 pull_request。本次查询命令退出码为 0。

| 远端检查                                                                  | 结果         |
| ------------------------------------------------------------------------- | ------------ |
| frontend：Install frontend dependencies                                   | success      |
| frontend：Check frontend formatting                                       | success      |
| frontend：Run frontend lint                                               | success      |
| frontend：Run frontend typecheck                                          | success      |
| frontend：Run frontend tests                                              | success      |
| frontend：Build frontend                                                  | success      |
| repository-quality                                                        | success      |
| software / backend-quality-baseline / harness / benchmark / configuration | 全部 success |

CI 使用 workflow 中固定的 Node.js 20.19.0、pnpm 10.15.1。此次远端验证对应接入格式门禁的新 SHA，不再使用旧 SHA 的成功结果代替。API 返回步骤与 job 结论；未下载测试日志，远端测试数量 UNKNOWN，本地 99 个前端测试和 40 个配置测试的数量记录仍保留为本地证据。

本任务验收通过：已测量和清除债务，明确决定接入，新增步骤只位于现有 frontend job，回归与对应新 SHA 的远端验证均成功。未合并 PR；合并不属于此任务验收要求。本次仅回填文档中的实际 CI 结果，没有新提交或推送。

## 最终审查与文档卫生

独立审查 verdict 为 **pass**，findings 为空，无延期问题。审查覆盖完整 6 文件 diff，独立重跑 `pnpm --dir frontend format:check` 和 `git diff --check`，退出码均为 0。该结论覆盖本地接入；新 SHA 的远端 CI 也已核验为 success。

`git diff --check`、`git diff --stat` 与 `rg -n "standard-agent-harness-reference|harness-execution|BATCH-[0-9]+" AGENTS.md docs` 均退出 0；没有六文件范围外的改动。

## 回滚

撤销本轮 6 文件的接入补丁即可移除格式步骤、脚本、工具依赖和配置，恢复上一轮清债后的状态；保留 `3a52d15` 的清债成果。不涉及数据库、生产部署或外部业务副作用。回滚或提交前先检查工作区，避免覆盖后续用户改动。
