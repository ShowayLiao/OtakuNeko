# OtakuNeko Anime Agent Benchmark v1 — 设计与用例包

本包用于交给 Codex **接入 OtakuNeko 当前 Harness**。它是一套**设计规范、固定测试夹具与 12 道场景定义**，不是已经接入仓库、可以直接调用真实模型的成品。

## 文件
- `docs/RFC-ANIME-AGENT-BENCHMARK.md`：架构、判分、隔离、CI 策略与验收标准。
- `docs/CODEX-IMPLEMENTATION-PROMPT.md`：可直接发给 VS Code 中 Codex 的任务指令。
- `cases/anime_benchmark_v1.jsonl`：12 个真实 Agent 场景的结构化定义（编排与断言需由 Codex 映射实现）。
- `fixtures/*.synthetic.json`：明确标记为**虚构**的作品、收藏、日程、搜索快照；不应混入线上用户数据。
- `scripts/validate_suite.py`：仅做用例与夹具静态检查，不会请求模型或执行 Agent。

## 本包现在可以运行的命令

```powershell
python scripts/validate_suite.py
```

## 仓库中的真实运行命令

```powershell
uv run --directory backend python -m app.evaluation.anime_live --provider real --isolated --suite smoke
uv run --directory backend python -m app.evaluation.anime_live --provider real --isolated --suite regression
```

Windows 上也可以从仓库根目录双击 `run-live-anime-benchmark.cmd` 运行 Smoke 并打开报告。完整操作步骤、状态含义、基线比较和扩展方式见 [`docs/architecture/anime-agent-benchmark-v1.md`](../docs/architecture/anime-agent-benchmark-v1.md)。

没有 Provider 凭据时入口会生成 `NOT_RUN` 报告，不会切换到假模型或生成分数。`regression` 报告会列出完整 12 道题；当前未实现的场景标为 `UNSUPPORTED`。

## 不可妥协的原则

1. 真模型、真 Router/Harness/Agent Runtime/Tool Call 路径；可以替换外部工具后端和用户数据，但不能伪造模型决策。
2. 所有写入只发生在测试数据库和测试日历，严禁真实用户账户、真实收藏或第三方生产日历修改。
3. 数据在每次 Case 和每次 Repeat 前重置，时钟固定，搜索快照可重复。
4. 最终状态优于“必须调用某个固定工具名称”；不因 Agent 选择合法替代路径而误判。
5. 明确区分 PASS、FAIL、ERROR、SKIP、UNSUPPORTED；没有模型密钥或评估能力不能记 PASS。
6. 默认 PR 不依赖付费 API；显式开启真实模型门禁，限制运行次数、步数、耗时与预算。
