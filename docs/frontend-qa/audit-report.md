# Agent 前端 QA 审计报告

日期：2026-10-21。独立前端任务，未创建 Harness Batch、commit、PR 或推送。基线分支 `feature-harness`，HEAD `13312ad0dea8107c86e889dbe42e05bf5c24931e`。初始工作区干净；随后出现的 collections capability 后端变更已由用户确认属于并行工作，予以保留并排除本次 Review 范围。

## 交付物与工作流

- [功能清单](feature-inventory.md)、[验收矩阵](acceptance-matrix.md)。
- 项目 Skill：`.agents/skills/frontend-qa/SKILL.md`，由 AGENTS/README 引用。
- Playwright：`frontend/playwright.config.ts`、`playwright.smoke.config.ts`、`e2e/fixtures.ts`、`agent.mock.spec.ts`、`backend.smoke.spec.ts`、`start-backend.mjs`。
- CI：`.github/workflows/frontend-qa.yml`，独立 Mock/Smoke 作业，PR 与手动触发，只读仓库权限，证据保留七天。同步更新现有配置覆盖 allowlist 与回归测试，避免新增工作流破坏旧门禁。
- `.gitignore` 仅放行本任务三份文档与 frontend-qa Skill；本地计划、其他 skills、日志、数据库、截图、trace 仍被忽略。未改动既有 Vitest 断言，仅将收集范围限定到 src 中的 `.test.ts/.tsx`，防止 E2E 被 Vitest 收集。

采用闭环：功能发现 → 清单/验收 → 浏览器复现 → 失败测试 → 最小修复 → E2E → 独立 Review → 修复/回归 → agent-browser 复核 → 报告。每个后续批次先根据矩阵确定范围，不能将未实现能力计入通过项。

## 环境与基线

真实配置：Next.js 16.1.6 / React 19.2.3 / Vitest 4.1.10 / TypeScript；Playwright Test 固定 1.64.1，锁文件由 pnpm 10.15.1 更新。主机 Node 24.12.0，初期全局 pnpm 11.0.9；最终门禁改用 `npx --yes pnpm@10.15.1`。CI 使用 Node 20.19.0 / pnpm 10.15.1，本地未模拟整套 Linux runner，不能据此宣称远端 CI 已通过。

- agent-browser MCP core 能发现，但 open 调用等待 300 秒后超时；按仓库规则改用独立命名 CLI 会话，成功读取 DOM、点击/填写、截图、Console/errors 和 Network。
- 未发现 Playwright MCP；本任务未安装/使用 Playwright MCP。E2E 使用 Playwright Test CLI。
- Playwright 初次缺少 Chromium，下载因 ECONNRESET 失败；复用已有 agent-browser Chromium 152.0.7977.54，通过 `E2E_CHROMIUM_EXECUTABLE_PATH` 显式指定。CI 使用 Playwright 默认安装。
- Shell 初期忽略 workdir 落在 C 盘；显式切换 E 盘仍被 sandbox 拒绝。受审查的提权命令可以访问授权仓库，后续显式 Set-Location；没有自动审批拒绝或覆盖用户文件。
- 前端 QA 端口 3100；Smoke 后端端口 8100。真实后端由脚本在临时工作目录启动，使用新 SQLite/checkpoint、随机 JWT 和合成账号，不继承 .env/provider key，禁用 qB、scheduler。无需生产数据库、Redis 或真实 LLM。
- 初始 Vitest：14 文件、99 测试通过（exit 0）。空聊天页是正常 Empty 状态，缺 Key 发送显示 configuration_error 是已有错误路径，不是“页面空白”或模型能力失败。

## 实际修复

| 问题与证据 | 最小改动 | 回归 |
|---|---|---|
| 移动端 390px 下搜索按钮右边缘 x=523，被外层 overflow 裁切。 | ChatInput 工具栏改为可换行的原生 flex；保留原有模型、角色、搜索、清除和连接控件。 | 三视口 layout E2E。 |
| DELETE 500 后本地会话直接消失且无提示。 | fetcher 检查 HTTP status；页面等待成功才删除，防重复请求、检查请求 token；失败显示 role=alert。 | failed delete E2E。 |
| 匿名用户信息读取将正常缺 token 当异常写 Console。 | Header 缺 token 时直接进入未登录状态，不抛错。 | 匿名浏览器复核与现有请求测试。 |
| EmotionGlobal SSR 样式节点与客户端 hydration 不一致；偏好主题还会使首次快照不同。 | LobeProvider 使用一致的 SSR 快照，hydration 后读取偏好/启用全局样式；不 suppress 或忽略 hydration 错误。 | 默认/保存暗色主题 E2E，pageerror 强断言。 |
| 新建会话按钮只有 tooltip，缺少可访问名称。 | 添加 aria-label；未重写会话组件。 | history/search/create E2E。 |
| 生成中 Enter 可再次触发发送。 | ChatInput handleSend 在 loading 时返回。 | 保留流式加载状态检查；独立键盘连发压力用例仍未覆盖。 |
| auth 变化时已失去 token，原 durable 分支仍发取消且不 abort。 | auth 变化只脱离本地流；正常用户取消仍等待服务端 terminal event。不宣称后台 Run 已被取消。 | Hook 与 auth invalidation E2E。 |
| Review-001：abort reject 仍写回旧会话；页面 resume effect 还可能回放旧 Run。 | abort 前递增 generation，取消待发布批处理；auth detach 不写旧消息；auth 事件先清 Store/置 loading，resume 仅在认证且有 token 时执行。 | reset 后 AbortError 回归与浏览器 auth invalidation。 |
| Review-002：旧 token A 的迟到 DELETE 401 清掉新 token B。 | 只有当前 token 仍等于请求 token 时才 invalidateAuth。 | stale DELETE401 / same-token401 两条单测。 |

未调整公共 API/SSE 协议、业务数据库、模型框架或后端 Runtime。最终视觉复核额外发现 Send 被固定输入高度裁切，补充样式就绪后的按钮底部几何断言：生产构建 RED 1 failed（bottom=878.39 > 844，exit1）；修复采用 ResizeObserver 测量工具栏并增加输入高度，输入区改回正常 flex 流，移除过期的消息区固定底部 padding。生产构建三视口 33 项回归全部通过（exit0），并保存 RED trace/screenshot。

## 测试可信度

Mock 覆盖 Empty、缺配置、空白输入、分阶段 Loading/工具调用/文本/Success、HTTP503 后下一次发送恢复、已登录历史刷新/搜索/新建、DELETE500、三视口布局/移动抽屉、durable cancel、cursor replay 去重、timeout 保留部分回答、保存主题和认证失效清空旧流。

真实 HTTP SSE fixture 按测试控制分阶段发送，先断言中间状态再释放下一阶段；其余 route.fulfill 只断言协议帧和最终展示。严格拒绝未 Mock API；所有 Mock E2E 检查未捕获 pageerror。诊断附件不包含消息正文、认证头、查询串；trace 本身仍可能包含完整 DOM/请求，故仅用于合成数据，禁止对真实个人账户采集。

Smoke 不 Mock API，经 Next proxy 访问真实 FastAPI，验证新账号登录、线程列表、刷新显示、匿名线程请求401。它不验证真实 Provider 推理、工具执行或 Run 恢复。

## 命令与结果

所有命令从仓库根目录执行。下表记录最终结果；环境失败/RED 另外列出。下列最终命令均使用 pnpm 10.15.1；后续文档核对不改变已测源码。

| 命令 | 退出码 | 结果 |
|---|---|---|
| `pnpm --dir frontend test`（初始） | 0 | 14 文件 / 99 passed。 |
| `pnpm --dir frontend test:e2e`（第一次完整稳定结果） | 0 | 30 passed；后续添加 auth 回归，需再次验收。 |
| `pnpm --dir frontend test:e2e:smoke` | 0 | 1 passed。 |
| `pnpm --dir frontend lint` | 0 | 0 errors / 94 warnings。 |
| `pnpm --dir frontend typecheck` | 0 | 通过。 |
| `pnpm --dir frontend test`（第一轮修复） | 0 | 14 文件 / 100 passed。 |
| `pnpm --dir frontend build`（第一轮修复） | 0 | Next build 完成。 |
| `pnpm --dir frontend exec vitest run src/lib/fetcher.test.ts src/__tests__/components/chat/useChatStreaming.test.tsx` | 0 | Review remediation 后 43 passed。 |
| `uv run --directory backend pytest tests/test_configuration_coverage.py -q`（临时测试 JWT） | 0 | 8 passed。 |
| `uv run --directory backend ruff check scripts/check_configuration_coverage.py tests/test_configuration_coverage.py` | 0 | 通过。 |
| `npx --yes pnpm@10.15.1 --dir frontend lint` | 0 | 最终 0 errors / 94 warnings。新增 .runtime/** 排除生成报告。 |
| `npx --yes pnpm@10.15.1 --dir frontend format:check` | 0 | 全部匹配文件通过。 |
| `npx --yes pnpm@10.15.1 --dir frontend typecheck` | 0 | 最终通过。 |
| `npx --yes pnpm@10.15.1 --dir frontend test` | 0 | 最终 14 文件 / 103 passed / 0 failed / 0 skipped。 |
| `npx --yes pnpm@10.15.1 --dir frontend build` | 0 | 最终生产构建通过。 |
| `E2E_EXTERNAL_SERVER=1` + `npx --yes pnpm@10.15.1 --dir frontend test:e2e`（本地生产构建 3100） | 0 | 最终 33 passed / 0 failed / 0 skipped；通过前已执行 build 和 start。设置已定位 Chromium 路径。 |
| `npx --yes pnpm@10.15.1 --dir frontend test:e2e:all`（显式已定位 Chromium） | 0 | 最终托管开发服务 33 Mock passed + 1 真实后端 Smoke passed；0 failed / 0 skipped。 |

RED/诊断记录：缺浏览器的两条 E2E exit1（启动前失败）；初始产品复现6条 exit1（1通过/5失败，包含 hydration）；首次 detach 单测 exit1（1 failed/7 skipped）；Review-001 reject/reset 单测 exit1（1 failed/40 skipped）；Review-002 测试 exit1（1 failed/1 passed/32 skipped）；新增 CI coverage 回归 exit1（1 failed/7 passed），修复后8通过。新增 auth 浏览器回归第一次33项 exit1（30 passed/3 failed），严格未 Mock 路由揭示旧 Run 自动回放，随后补清空与认证 guard。中间另有 fixture 线程范围、选择器多匹配和脚本编码错误，均按测试问题定位修正，未放宽 pageerror 断言。普通检查命令和测试发现不计入浏览器通过。

## 独立 Review 与再验证

独立 Reviewer 采用新上下文、只读审查完整任务 diff 和新文件，排除明确属于用户的并行业务变更。第一轮 verdict：changes_required，1 high、1 medium（见上表）。已完成对应 RED/GREEN 修复；第二轮源码审查确认两项修复，无新增源码 Finding；随后浏览器找出 Send 裁切并进行额外视觉 remediation，独立 Reviewer 也审查了 ResizeObserver/布局与强化断言，未发现实质源码问题。最终独立 Reviewer verdict 为 pass，无未处理 Finding。第 1 轮 changes_required，第 2 轮完成竞态修复、视觉 remediation 追加审查与最终文档核对。Review 后已完成三视口 agent-browser 复核，不将开发者自检当作独立 Review。

Skill 经过无 Skill/有 Skill 的只读压力场景检验：测试发现不能当浏览器通过、Mock 不能代表真实 Agent、x523 不能凭截图判通过、预设 Run ID 不能代表刷新恢复、并行文件必须归属确认。基线 Reviewer 已能遵守多数边界，未伪造“Skill 从失败到成功”的效果；Skill 的价值是把本项目工具/契约/证据路径固化。

## 边界与剩余事项

- 已通过浏览器验证：Desktop 1440×900、Tablet 768×1024、Mobile 390×844 已对生产构建目视检查；会话抽屉开关、新建、搜索无结果、输入、实际点击 Send 和缺配置错误路径均已操作。最终 Send bottom 分别为 863/900、991.16/1024、807.45/844，无明显溢出。最终 Console/errors 输出为空，Network 未捕获 4xx/5xx；缺配置路径未发 API 请求，不能据此声明后端业务成功。
- 仅通过 Mock 测试：流式文本/工具展示、取消、回放、timeout 和错误恢复；这些通过不证明真实 Agent 业务能力。
- 未验证：真实 LLM/工具副作用、已认证进行中 Run 刷新恢复、搜索引用完整链路、消息编辑/重生成/复制 E2E、远端 GitHub Actions、Firefox/WebKit/真实移动设备。
- 已知限制：history 缺 Run 元数据，刷新进行中的 Run 不可从当前历史加载路径恢复；MCP 徽标数据来自聊天 fetch，不是 MCP 健康探测；编辑/重新生成当前采用追加行为，产品语义未确认。不把后两项主观判断为已修复 Bug。
- 已知警告：94 ESLint warning；antd Modal maskClosable 弃用；Node NO_COLOR/FORCE_COLOR、Next proxy util._extend 弃用提示。没有隐藏这些警告或通过删除失败断言制造成功。
- 后端全量 pytest/Ruff/Eval 未运行：本任务未改动 Harness/业务；仅必要 CI 配置覆盖脚本及其测试有定向验证。全量后端同时被另一任务修改，不能把其状态冒认为本任务结果。
- 本地 `next start` 实际可访问，但提示 output:standalone 应使用 standalone server；本轮没有验证 standalone 打包部署。
- Actionlint/完整配置工具链、本机 Node20、远端 PR 执行未验证；新工作流的语法/契约由审查与仓库回归覆盖，远端执行结果仍需实际 CI。

回滚：仅撤销本任务列明文件的 diff、移除本任务新增 QA 文件和精确 ignore 例外；保留所有并行业务修改。无数据库迁移、生产配置或外部状态变更。临时 SQLite 与生产数据隔离；结束仅本任务服务/浏览器会话。不要使用 reset --hard、全量 add 或批量清理用户目录。

## 最终浏览器证据

三张已目视检查的截图位于 ignored `.runtime/frontend-qa/final-desktop.png`、`final-tablet.png`、`final-mobile.png`；缺配置点击证据为 `final-mobile-error.png`。Send 裁切 RED 为同目录 `send-clipping-red.png` 和 `send-clipping-red-trace.zip`。这些仅含合成文本，不随 Git 分发。

## 本任务修改文件范围

- `.gitignore`、`AGENTS.md`、`README.md`，三份 `docs/frontend-qa/*.md` 和 `.agents/skills/frontend-qa/SKILL.md`。
- `frontend/package.json`、`pnpm-lock.yaml`、`vitest.config.ts`、`eslint.config.mjs`、两个 Playwright config；`frontend/e2e/` 下四个文件。
- `frontend/src/components/chat/ChatInput.tsx`、`SessionPanel.tsx`、`index.tsx`；`components/header/User.tsx`；`components/providers/LobeProvider.tsx`；`hooks/useChatStreaming.ts`；`lib/fetcher.ts` 和 `fetcher.test.ts`；`src/__tests__/components/chat/useChatStreaming.test.tsx`。
- `.github/workflows/frontend-qa.yml`；必要的 `backend/scripts/check_configuration_coverage.py` 与 `backend/tests/test_configuration_coverage.py`。
- 其它 backend capability/harness/service/repository/schema/contract-test 文件属于用户确认的并行工作，未覆盖、暂存、提交或清理，未纳入本任务成功断言。

Mock fixture 最后按当前 `AgentRuntime.stream_decision` 的实际 emit 投影核对：初始元数据帧使用 `message_input`（而非源码不发出的 run_started），JSON 包含 `type/run_id/sequence`，不虚构 wire schema_version。此项只改测试夹具，另行重跑全部 Mock E2E；它不改变产品代码或真实后端协议。

最终协议夹具校正后，`E2E_CHROMIUM_EXECUTABLE_PATH=<已定位本地 Chromium>` + `npx --yes pnpm@10.15.1 --dir frontend test:e2e` 再次 exit 0：33 passed / 0 failed / 0 skipped；对应 fixture Prettier 和 typecheck 均 exit 0。最终仅本任务的浏览器会话已关闭，3100/8100 QA 服务无剩余监听。

## 独立 Review 最终结论

Reviewer 未参与实现，独立读取完整任务 diff、新文件、回归和三张最终截图；实际命令结果由协调者执行并提供，Reviewer 没有声称自己重跑全部命令。未覆盖功能列在上方限制内，pass 针对本任务工作流与已记录修复。

```yaml
review_result:
  batch: null
  kind: documentation
  verdict: pass
  summary: 两项认证竞态已修复；视觉追加修复、协议 fixture、QA/CI/Skill 和文档审查通过。
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
    - command: npx --yes pnpm@10.15.1 --dir frontend lint
      exit_code: 0
    - command: npx --yes pnpm@10.15.1 --dir frontend format:check
      exit_code: 0
    - command: npx --yes pnpm@10.15.1 --dir frontend typecheck
      exit_code: 0
    - command: npx --yes pnpm@10.15.1 --dir frontend test
      exit_code: 0
    - command: npx --yes pnpm@10.15.1 --dir frontend build
      exit_code: 0
    - command: npx --yes pnpm@10.15.1 --dir frontend test:e2e
      exit_code: 0
    - command: npx --yes pnpm@10.15.1 --dir frontend test:e2e:all
      exit_code: 0
    - command: uv run --directory backend pytest tests/test_configuration_coverage.py -q
      exit_code: 0
    - command: uv run --directory backend ruff check scripts/check_configuration_coverage.py tests/test_configuration_coverage.py
      exit_code: 0
    - command: git diff --check
      exit_code: 0
  reviewed_files:
    - .gitignore
    - AGENTS.md
    - README.md
    - .github/workflows/frontend-qa.yml
    - .agents/skills/frontend-qa/SKILL.md
    - docs/frontend-qa/feature-inventory.md
    - docs/frontend-qa/acceptance-matrix.md
    - docs/frontend-qa/audit-report.md
    - frontend/package.json
    - frontend/pnpm-lock.yaml
    - frontend/eslint.config.mjs
    - frontend/vitest.config.ts
    - frontend/playwright.config.ts
    - frontend/playwright.smoke.config.ts
    - frontend/e2e/fixtures.ts
    - frontend/e2e/agent.mock.spec.ts
    - frontend/e2e/backend.smoke.spec.ts
    - frontend/e2e/start-backend.mjs
    - frontend/src/components/chat/ChatInput.tsx
    - frontend/src/components/chat/SessionPanel.tsx
    - frontend/src/components/chat/index.tsx
    - frontend/src/components/header/User.tsx
    - frontend/src/components/providers/LobeProvider.tsx
    - frontend/src/hooks/useChatStreaming.ts
    - frontend/src/lib/fetcher.ts
    - frontend/src/lib/fetcher.test.ts
    - frontend/src/__tests__/components/chat/useChatStreaming.test.tsx
    - backend/scripts/check_configuration_coverage.py
    - backend/tests/test_configuration_coverage.py
  deferred_findings: []
```
