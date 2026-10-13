# Frontend 格式债务与门禁决策

日期：2026-10-13。当前状态：**格式债务已清零，format:check CI 门禁尚未接入**。

## 范围与基线

基线为 `feature-harness` 的 `e124dc7866ba43deef7500054a5ecc6972637840`，普通检出，无活动 Harness Batch。评估开始时工作区干净；清债开始时唯一已有改动是本决策文档，由上一轮评估生成，本轮继续更新。

`.github/workflows/ci.yml` 的 `jobs.frontend` 独立执行 lint、typecheck、test、build；CI 固定 Node.js 20.19.0、pnpm 10.15.1。`frontend/package.json` 尚无格式脚本和 Prettier 依赖。

清债使用 **Prettier 3.6.2、默认 80 列、无插件、不加载配置或 EditorConfig、固定 LF**。只处理基线中 110 个前端跟踪文件：ts/tsx/js/mjs/cjs/css/json/md/yaml，排除生成的 `pnpm-lock.yaml`、静态二进制与非格式化文件。本记录另外格式化，不计入基线债务统计。未改动工作流、依赖、脚本或后端。

## 原始债务与评估决定

| 候选规则         | 检查文件 | 格式债务文件 |  比例 | 预计新增行 | 预计删除行 |
| ---------------- | -------: | -----------: | ----: | ---------: | ---------: |
| 默认规则，80 列  |      110 |          104 | 94.5% |      9,139 |      5,895 |
| 默认规则，120 列 |      110 |          104 | 94.5% |      6,589 |      6,140 |

原始评估使用只读检查；预计 diff 由临时目录中的格式副本和逐文件 `git diff --no-index --numstat` 汇总，测量程序退出码 0。使用 `endOfLine=auto` 排除 checkout 换行差异时，两种行宽的债务检查均退出 1，输出 104 个文件。

使用固定 LF 时，检查报告 105 个文本不同的文件，其中 `frontend/pnpm-workspace.yaml` 只有 CRLF/LF 差异，Git numstat 为 0/0。因此历史格式债务数为 104，另有 1 个本地换行差异。首次宽泛 glob 探测读到忽略的 UTF-16 诊断 JSON，退出码 2，已作废；正式统计和清债均使用显式跟踪文件列表。

初次决定暂缓阻塞式格式门禁，原因是立即接入会因既有债务使 frontend job 失败，而清债会触及跨组件的大范围机械 diff。用户随后明确要求清除债务，因此本轮执行机械格式化。

## 清债结果

- 历史债务文件：104 → 0；固定 LF 检查：105 → 0。
- 最终检查覆盖基线 110 个文件；Git 实际 diff 为 **104 个文件、9,104 行新增、5,882 行删除**。YAML 换行统一在 Git 规范化后不产生内容 diff。
- 全部改动逐文件与基线经同版本 Prettier 生成的稳定输出比较：110 个文件一致，无范围外源码修改，无不稳定输出。
- `frontend/src/lib/fetcher.test.ts` 的第一次与第二次格式化存在链式调用换行差异。已在首个测试块中最小复现，并比较 TypeScript AST：原文、第一次和第二次输出的节点结构与字面值相同。该文件第二次格式化后稳定，全范围最终 `--check` 和 `--debug-check` 均通过。
- 此轮仅做机械格式化，未修改测试断言、应用行为、API 或组件布局。未新增镜像实现的测试。

从仓库根目录复现检查：

```powershell
$formatFiles = @(git ls-files frontend | Where-Object {
    $_ -match '\.(tsx?|[cm]?js|css|json|md|yaml)$' -and
    $_ -notlike '*/pnpm-lock.yaml' -and
    $_ -ne 'frontend/FORMAT_CHECK_DECISION.md'
})
pnpm dlx prettier@3.6.2 --check --no-config --no-editorconfig --end-of-line lf @formatFiles frontend/FORMAT_CHECK_DECISION.md
pnpm dlx prettier@3.6.2 --debug-check --no-config --no-editorconfig --end-of-line lf @formatFiles
```

实际写入命令为上述基线文件列表上的 `pnpm dlx prettier@3.6.2 --write --no-config --no-editorconfig --end-of-line lf @formatFiles`，退出码 0；随后仅对 `frontend/src/lib/fetcher.test.ts` 以相同参数再写入一次，退出码 0。两次写入均未涉及未跟踪或忽略的诊断产物。原始 debug-check 的非幂等性失败已记录为工具问题，未通过删除测试或忽略文件掩盖。

## 验证

| 命令或检查                              | 退出码 | 结果                                        |
| --------------------------------------- | -----: | ------------------------------------------- |
| 清债前 `pnpm --dir frontend test`       |      0 | 14 个文件 / 99 个测试通过，失败 0、跳过 0   |
| 清债前 `pnpm --dir frontend lint`       |      0 | 0 错误、94 警告                             |
| 清债前精确范围 Prettier `--check`（LF） |      1 | 105 个文件存在差异                          |
| 清债后精确范围 Prettier `--check`（LF） |      0 | 110 个基线文件均合规                        |
| 清债后精确范围 Prettier `--debug-check` |      0 | 110 个基线文件一致性检查通过                |
| 基线到稳定格式输出的逐文件核对          |      0 | 110 个文件匹配；仅 1 个文件需要第二次格式化 |
| `pnpm --dir frontend lint`              |      0 | 0 错误、94 警告，与基线数量一致             |
| `pnpm --dir frontend typecheck`         |      0 | 通过                                        |
| `pnpm --dir frontend test`              |      0 | 14 个文件 / 99 个测试通过，失败 0、跳过 0   |
| `pnpm --dir frontend build`             |      0 | 生产构建通过，生成 8 个静态页面             |
| `git diff --check`                      |      0 | 无空白错误                                  |

本地宿主为 Node.js 24.12.0、pnpm 11.0.9，验证结果不能冒充 CI 固定工具链结果。Git 的 LF/CRLF checkout 提示是已知本地警告。94 个 lint 警告属于既有 lint 债务，未纳入本次格式清债。

未运行后端、Eval 或浏览器视觉检查：本次为机械源码格式化，没有后端、运行行为、UI 外观或交互修改。

## CI 与后续决定

既有基线 SHA 的 [CI run 38340876181](https://github.com/ShowayLiao/OtakuNeko/actions/runs/38340876181) 为 success；frontend 的安装、lint、typecheck、test、build steps 与全部 7 个 jobs 均为 success。该结果由上一轮只读 API 查询核验，不代表本轮未提交格式化改动的远端结果。

清债已移除最初暂缓的债务阻碍。当前交付停在清债完成；没有将格式检查接入 CI，没有提交、推送或触发新远端 CI。格式再生风险仍在。

若接入门禁，应将固定版本工具、前端配置和排除范围写入项目，在现有 `jobs.frontend` 安装后添加 `pnpm format:check`，保持其他 jobs、权限与触发条件不变；验证不合规输入确实失败，完成四项回归，并检查新提交的远端 frontend 和聚合 CI。不能将旧 SHA 的成功当作新门禁验证。

## 审查与回滚

清债 diff 的全范围确定性格式核对已通过。独立审查已完成 1 轮，verdict 为 pass，findings 为空；覆盖全部 110 个范围内跟踪文件及本记录，无未处理的阻塞问题。

回滚范围是此轮 104 个前端文件的机械 diff，以及本记录的清债状态更新。撤销本轮明确文件的补丁即可恢复基线格式；应先检查后续用户改动，避免整仓还原。没有运行时状态、数据库或外部副作用需要恢复。
