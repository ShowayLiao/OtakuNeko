# A-L0-02｜后端格式门禁

## 结论

后端 formatter check 已接入 `.github/workflows/ci.yml` 的 `backend-quality-baseline` job，**阻断式**执行：格式违规使 job 失败。门禁范围限定在 A-L0-01 已确立的首期架构边界（`app/harness`、`app/capabilities`、`app/memory`、`app/trace` 及其对应测试目录），范围外的 140 个文件不做任何重排，只以 `ruff format --diff` 产出差异报告并存为 CI artifact。

同时修正了 workflow 触发器缺陷：CI 原先只监听 `main`，而仓库默认分支是 `release-1.0`、集成工作发生在 `feature-*` 上，导致 CI 从不运行。`pull_request` 现在不加分支过滤，`push` 覆盖 `main` 与 `release-1.0`。

当前决策：**Accept / 进入下一项能力迭代**。阻断命令的通过态、失败态、幂等性与机械性均已在本地复现并存档；远端 Run 需通过 PR 触发，见「Artifacts」。

## 门禁范围与既有代码处理

| 项目 | 处理 |
| --- | --- |
| 阻断范围 | `app/harness`、`app/capabilities`、`app/memory`、`app/trace`、`tests/harness`、`tests/capabilities`、`tests/memory`、`tests/trace`（共 114 个 `.py`） |
| 范围内既有代码 | 一次性机械重排 88 个文件，单独成 commit，不含任何业务改动 |
| 范围外代码 | `app`、`tests`、`alembic`、`scripts` 其余 140 个文件**未改动**，仅进差异报告 |
| 阻断语义 | 范围外差异**不**阻断；范围内有差异即 job 失败 |

范围外不阻断是刻意的：如果让 `ruff format --check` 直接覆盖全后端，218 个既有文件必须在同一次改动里被重排，git blame 会大面积失效，而这与本次能力目标（建立门禁）无关。范围与 mypy 基线保持同一组边界，两个门禁的覆盖面因此可以对齐解读。

## 格式化契约

`backend/pyproject.toml` 新增：

```toml
[tool.ruff]
target-version = "py310"   # 与 requires-python = ">=3.10" 一致，不依赖 Ruff 的推断
line-length = 88           # 与差异基线测量时一致，改动此值会改变基线

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"         # 仓库无 .gitattributes 且 core.autocrlf=true，强制 LF 以免 Windows/Linux 产生不同字节
```

`ruff check app tests` 在本配置下仍退出 0（新增 `[tool.ruff]` 前该命令也无项目配置），没有引入新的 lint 规则变化；规则加严属于计划中的独立任务，本次未顺手扩大。

## 真实命令与退出码

命令以仓库根目录为起点，`UV_CACHE_DIR=.uv-cache` 仅用于规避本机 uv cache 写权限边界，CI runner 不依赖该目录。

| 命令 | 退出码 | 结果 |
| --- | ---: | --- |
| `uv run --locked --directory backend ruff format --check <8 个范围路径>` | 0 | `114 files already formatted` |
| 同上，重复执行 | 0 | 无新增 diff，幂等成立 |
| `uv run --locked --directory backend ruff check app tests` | 0 | `All checks passed!` |
| `uv run --locked --directory backend mypy` | 0 | `Success: no issues found in 60 source files` |
| `uv run --locked --directory backend deptry .` | 0 | 扫描 174 个文件，无依赖问题 |
| `uv run --locked --directory backend pytest` | 0 | **799 passed, 1 skipped**, 305 warnings |
| `uv run --locked --directory backend ruff format --check app tests alembic scripts` | 1 | 范围外 140 个文件待格式化（预期红，不接入阻断） |
| `git diff --check` | 0 | 无空白错误 |

### 失败证据（原文存档）

向门禁范围内注入一行未格式化代码，阻断步骤随即失败；撤销后恢复通过。原始输出如下，同时存于 `backend/.runtime/quality/format-gate-failure-evidence.txt`：

```text
$ printf "\nVIOLATION = {\"a\":1,\"b\":2}\n" >> app/harness/policy.py
$ uv run --locked ruff format --check app/harness app/capabilities app/memory app/trace tests/harness tests/capabilities tests/memory tests/trace
Would reformat: app\harness\policy.py
1 file would be reformatted, 113 files already formatted
[exit code: 1]

$ cp /tmp/policy.py.bak app/harness/policy.py   # revert the injection
$ uv run --locked ruff format --check app/harness app/capabilities app/memory app/trace tests/harness tests/capabilities tests/memory tests/trace
114 files already formatted
[exit code: 0]
```

## 差异报告

- 生成命令：`uv run --locked ruff format --diff app tests alembic scripts > .runtime/quality/format-debt.diff`
- 指标：**140 个文件待格式化**，`155` 个已符合，报告 `25244` 行（约 912 KB）
- 阻断前的对照：本次重排前，仅 `app tests` 就有 218 个文件待格式化（范围 8 路径内为 88/114）
- 报告落地：CI 以 artifact `backend-format-debt` 上传，`if-no-files-found: error`；本地副本在 `.runtime/quality/format-debt.diff`，被 `.gitignore:112` 的 `.runtime/` 覆盖，不入库

报告步骤与阻断步骤分离，`ruff format --diff` 的退出码 1 被捕获而不外传，已用 `bash -e` 复现：阻断步骤退出 1 时报告步骤仍退出 0，不会掩盖也不会伪造门禁结论。

## 机械性验证

仅凭 `ruff format` 自身声明不足以说明「既有代码未被无关重排」，因此对 **commit `4a74257` 的暂存内容**（88 个 `.py`）逐一与其 `HEAD` 版本比对：

1. **AST 等价**：`ast.dump` 比对 —— 88/88 一致，无一处语法树变化。
2. **评论保留**：`tokenize` 抽出的注释多重集比对 —— 88/88 一致，无注释被丢弃或改写。

两项均为 88/88 全绿，因此该 commit 是**可证明的纯机械变换**。

任务开始前工作区存在未提交改动，其中 `backend/app/harness/normalizer.py` 与 `backend/tests/harness/test_result_normalizer.py` 落在门禁范围内。这两个文件的重排与在途业务修改被**分开处理**：commit 只包含 `HEAD` 内容重排后的结果（AST 与 `HEAD` 相同），在途修改保留在工作区，因此 `git diff` 现在只显示业务改动本身（`normalizer.py` 11 行、`test_result_normalizer.py` 76 行，全部为新增）。`backend/app/api/v1/collections.py` 不在门禁范围内，未被 formatter 触碰。

## 回归结论、遗留风险与下一步

- 回归结论：Ruff、mypy、deptry、pytest 全部通过。`pytest` 在改动前为 `1 failed, 798 passed`（失败项是依赖出网的 `tests/mcp/test_stdio_e2e.py::test_tools_call_anime_search`），改动后为 `799 passed, 1 skipped`；该用例的通过与否取决于本机网络，与本次重排无关。格式重排未引入语义变化，未引入新的测试失败。
- 遗留风险一：范围外 140 个文件的格式债仍然存在且会继续增长，因为门禁不覆盖它们；债的可见性依赖 artifact 和本报告，不依赖阻断。
- 遗留风险二：`line-ending = "lf"` 依赖仓库当前无 `.gitattributes` 的事实；一旦引入 `.gitattributes` 做换行规范化，应重新确认两者是否冲突。
- 遗留风险三：`tests/mcp/test_stdio_e2e.py` 依赖真实出网，在受限网络环境下会超时失败，属于既有的环境敏感用例，不是门禁问题，但会让 `software` job 在网络受限的 runner 上产生噪声。
- 遗留风险四：`pull_request` 不加分支过滤会让所有 PR 都跑质量 job，PR 数量增长后 CI 时长会线性上升；若成为瓶颈，应收窄到 `[main, release-1.0]` 再加 `feature-*` 通配。
- 下一步：开 PR 触发首次真实 Run 并回填 Run 编号与 artifact；随后把门禁范围按模块逐步扩面（每次扩面都要求该模块先独立完成一次机械重排），直到覆盖 `app`/`tests`/`alembic`/`scripts` 全部 295 个文件。

## Artifacts

- PR/Commit：commit `4a74257`（`style(backend): format the architecture boundaries with ruff`，89 文件）承载格式基线与契约；紧接其后的 `ci: gate backend formatting and run CI on every pull request` 承载门禁接线、触发器修正与本报告（其自身 hash 不在此列出，因为任何后置修改都会改变它）。两个 commit 均已推送到 `origin/feature-harness`；PR 待创建。
- Run/Eval：本地通过态、失败态（原文存档）、幂等与机械性验证均已完成。GitHub Actions 远端 Run 未执行——触发器已修好，但 `feature-harness` 的 push 不在 `push.branches` 内，需要开 PR 才会产生 Run；本机无 `gh` CLI，PR 需在网页创建。
- Report：本文件；失败证据原文 `backend/.runtime/quality/format-gate-failure-evidence.txt`；差异报告为 CI artifact `backend-format-debt`（本地副本 `backend/.runtime/quality/format-debt.diff`，不入库）。

## 回滚

本次改动落在 `backend/pyproject.toml`（新增 `[tool.ruff]`、`[tool.ruff.format]`）、`.github/workflows/ci.yml`（触发器 + `backend-quality-baseline` 新增 3 个步骤）、88 个已格式化的后端文件，以及本报告。回滚 `4a74257` 即可撤销格式基线与契约；回滚第二个 commit 即可撤销门禁接线与触发器修正。回滚时不得覆盖工作区中任务开始前已存在的未提交修改（`backend/app/api/v1/collections.py`、`backend/app/harness/normalizer.py`、`backend/tests/harness/test_result_normalizer.py`、`backend/tests/api/test_collections_query_bounds.py`）。
