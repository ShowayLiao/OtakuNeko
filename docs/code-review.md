# OtakuNeko Code Review Standard

## 1. 目的和适用范围

本规则用于审查 OtakuNeko 的业务代码、Agent Harness、前后端协议、审计/任务文档和执行记录。目标是发现真实的正确性、权限、安全、恢复、兼容、可观测性和测试可信度问题。

Review 不是格式化、lint 或实现过程复述。机械问题交给自动化工具；Reviewer 重点检查工具难以证明的架构边界、运行语义和失败路径。

如果当前没有明确活动 Batch，Reviewer 仍可以审查文档或普通变更，但不得把任务规划当作已完成实现，也不得凭空生成 Batch 验收结论。

## 2. Reviewer 输入和顺序

Reviewer 必须按以下顺序建立上下文：

1. <code>docs/architecture/standard-agent-harness-reference.md</code>；
2. <code>docs/standard-agent-harness-reference-and-codex-audit-guide.md</code>；
3. 相关 <code>docs/harness-audit/*.md</code>；
4. 当前任务和 <code>docs/harness-tasks/INDEX.md</code>；
5. 当前路径下更具体的 <code>AGENTS.md</code>；
6. 完整未提交 diff；
7. 执行记录中的真实命令、退出码和测试结果。

Review 前必须确认：

- 修改文件属于任务允许范围；
- 工作区中已有修改已被识别并与当前 diff 区分；
- 任务引用的路径、符号和命令在仓库中存在；
- 测试确实执行，而不是只新增测试文件或复制历史结果；
- 代码、审计和目标架构之间的不一致已经记录。

没有源码或命令证据的问题不能作为确定性 Finding；应标记为“需要确认”，并列出需要补充的证据。

## 3. 证据规则

每个 Finding 必须包含：

- 精确文件路径；
- 符号、路由、配置项或文档章节；
- 具体行为或缺失证据；
- 对用户、数据、权限、运行状态或维护的影响；
- 可验证的修复动作。

优先使用源码行号、测试名称、命令退出码和执行记录。目标架构中的 MUST 不能单独证明当前代码已经实现；类名、配置项、接口声明和测试名称也不能代替真实调用路径。

以下内容不能作为充分证据：

- “应该会失败”或“看起来不安全”；
- 只引用 README 或计划而不核对源码；
- 只审查最后一次修改的几行；
- 只看到测试文件存在就声称测试通过；
- 用 Prompt、注释或前端隐藏字段证明服务端授权；
- 用 SSE 已发送 sequence 证明 Run 已持久化。

## 4. 严重度和提交门槛

### Blocker

无法安全审查或无法判断变更是否正确：

- diff 不完整或混有无法归属的用户修改；
- 关键命令、退出码或生成依赖缺失；
- 任务与实现范围无法对应；
- 文档引用的核心文件不存在且会导致执行流程错误。

Blocker 存在时不得提交。

### Critical

可能造成严重安全、数据或权限事故：

- 跨用户/跨租户访问；
- Secret、BYOK、JWT 或密码泄漏；
- 模型获得任意 SQL、Shell、文件或网络访问；
- 未授权删除、下载、发送、扣费、发布或 qBittorrent 操作；
- 重试导致不可逆副作用重复执行；
- 可绕过 Runtime、Policy、审批或 Domain Authorization。

Critical 存在时不得提交，也不得继续后续 Batch。

### High

很可能造成生产故障或核心 Harness 语义错误：

- 存在两个互相竞争的 Run 编排中心；
- LangGraph、HTTP Controller 或 Tool 绕过 Runtime；
- Run 无法终止、取消、恢复或产生唯一 terminal state；
- SSE 断开导致状态丢失或重复执行；
- Tool 绕过资源级授权；
- Provider 对象泄漏到业务层；
- 错误、重试、预算或取消可能造成无限循环；
- 公共 API、SSE 事件或数据 Schema 被意外破坏。

High 存在时不得提交。

### Medium

重要但影响范围受限：

- Tool/Capability Schema、版本或错误分类不完整；
- 缺少关键失败、幂等、取消或恢复测试；
- Context、Memory、Tool output 或日志无界或缺少信任标签；
- Event 缺少恢复、审计或关联字段；
- 配置、迁移或执行记录缺少版本和回滚说明；
- 新文档把审计建议写成当前实现，或关键路径引用错误。

Medium 原则上必须在当前变更修复；延期时必须有负责人、后续任务和理由。

### Low

非阻塞改进：

- 局部命名、文档可读性或非关键测试可维护性问题。

Low 可以延期，但必须记录原因和后续任务。

## 5. OtakuNeko 专项检查

### 5.1 变更范围和文档一致性

检查：

- 是否只修改当前任务允许文件；
- 是否误改业务表、依赖、前端协议或生成文件；
- 规划、审计、执行记录和源码事实是否分层；
- <code>docs/architecture/</code>、<code>docs/harness-audit/</code>、<code>docs/harness-tasks/</code>、<code>docs/harness-execution/</code> 的相对链接是否有效；
- 是否创建了没有活动 Batch 对应关系的执行记录；
- 是否把未实现的 Run Coordinator、Event Store、Decision 或 Approval 写成已存在。

### 5.2 Runtime Ownership 与 LangGraph 边界

重点源码：

- <code>backend/app/harness/runtime.py</code>
- <code>backend/app/agents/graph.py</code>
- <code>backend/app/agents/langgraph_adapter.py</code>
- <code>backend/app/harness/routing_adapter.py</code>
- <code>backend/app/api/v1/agent.py</code>

确认：

- 一次 Run 只有一个控制者；
- Runtime 控制循环、预算、取消、重试和 terminal result；
- LLM 只产生结构化 Decision；
- ChatWorkflow 作为 LangGraph adapter 时不会绕过 Runtime；
- HTTP Controller 只做 ingress、依赖组装和事件投影；
- Tool 内没有隐藏另一个自由运行的 Agent Loop；
- Graph error event 不会被 generator 正常结束掩盖为 success；
- feature flag fallback 不会绕过副作用 Policy。

### 5.3 Decision、Invocation 和结果契约

重点源码：

- <code>backend/app/harness/task.py</code>
- <code>backend/app/harness/state.py</code>
- <code>backend/app/harness/result.py</code>
- <code>backend/app/harness/capability_adapter.py</code>
- <code>backend/app/capabilities/types.py</code>
- <code>backend/app/capabilities/registry.py</code>
- <code>backend/app/mcp_server/</code>

确认：

- Decision、Invocation、Result、Event 有版本、Schema 和稳定 ID；
- 未知 Decision、能力名和字段被安全拒绝；
- 执行前经过 Schema、Policy 和资源授权；
- user_id 不出现在可伪造的模型参数中；
- Tool、Capability、MCP 和未来 Subagent 的语义没有混淆；
- safe output、错误 code/category、usage 和 provenance 能被下游消费；
- Legacy adapter 只保留兼容路径，不形成第二套状态机。

### 5.4 身份、租户和资源授权

重点源码：

- <code>backend/app/api/deps.py</code>
- <code>backend/app/api/v1/agent.py</code>
- <code>backend/app/api/v1/collections.py</code>
- <code>backend/app/api/v1/endpoints/schedules.py</code>
- <code>backend/app/capabilities/schedule.py</code>
- <code>backend/app/mcp_server/policy.py</code>

确认：

- principal 来自可信认证依赖或 Runtime Context；
- Tool 和 Domain Service 对资源再次授权；
- 查询、Thread、Memory、Trace 和写操作按用户/租户隔离；
- body、query、Tool 参数和 prompt 不能伪造身份；
- 日志、Trace、SSE 和 error detail 不泄漏 JWT、BYOK、密码或完整认证信息。

### 5.5 外部副作用、幂等和补偿

重点边界：

- <code>backend/app/api/v1/rss.py</code>
- <code>backend/app/services/qb_service.py</code>
- <code>backend/app/api/v1/collections.py</code>
- <code>backend/app/api/v1/endpoints/schedules.py</code>
- <code>backend/app/capabilities/schedule.py</code>
- Memory 写入、批量操作和文件写入。

对每个写操作检查：

- 是否显式标记 side effect、风险和审批要求；
- 是否有资源级授权；
- 是否有正确 scope 的幂等键；
- 相同 key + payload 是否 replay，冲突 payload 是否拒绝；
- timeout 后是否可能已成功；
- retry 是否会重复下载、删除、收藏、日程写入或发送；
- 取消后下游是否停止；
- 部分成功是否有 compensation/attention 状态；
- 审计事件是否记录安全字段；
- qBittorrent 路由是否 fail closed，而不是只依赖 ENABLE_QB_PROXY。

### 5.6 Run 生命周期、持久化、SSE 和恢复

重点源码：

- <code>backend/app/harness/checkpoint.py</code>
- <code>backend/app/agents/graph.py</code>
- <code>backend/app/api/v1/agent.py</code>
- <code>frontend/src/lib/fetcher.ts</code>
- <code>frontend/src/hooks/useChatStreaming.ts</code>
- <code>backend/app/trace/sql_store.py</code>
- <code>docker-compose.yml</code>
- <code>backend/alembic/</code>

确认：

- Run 状态转换合法且 Terminal 状态不会继续执行；
- Run、Step、Invocation、Event、Checkpoint 和幂等记录有明确 owner；
- sequence 单调，event/run/invocation 可以关联；
- SSE 断线不是 Run 丢失或成功；
- Last-Event-ID、Run 查询或 replay 不会重新执行已完成 Invocation；
- backend 重启、多 worker、SQLite/PostgreSQL 和卷挂载语义有测试或明确限制；
- Trace 是投影/审计，不被误当成完整 Run source of truth；
- 用户取消能传播到模型、Tool、Workflow 和 Subagent；
- waiting/approval 的 Run 可以暂停和恢复。

### 5.7 错误、超时、取消和预算

确认：

- 错误有稳定 code/category、retryable 和 terminal 语义；
- 参数错误、权限错误和不可幂等副作用不自动重试；
- Model、Tool、Step、Run 有独立 timeout/budget；
- 最大重试次数、总时间和 recursion limit 明确；
- Provider、Tool、Graph 和 Runtime 不会把异常堆栈/raw error 直接送给模型或用户；
- cancelled、timed_out、budget_exceeded、denied 和 failed 不被前端统一显示为 success；
- Generator 正常结束不会掩盖失败状态。

### 5.8 Context、Memory、Tool output 和安全

重点源码：

- <code>backend/app/memory/</code>
- <code>backend/app/agents/tools/base.py</code>
- <code>backend/app/agents/graph.py</code>
- <code>backend/app/trace/redaction.py</code>
- <code>frontend/src/hooks/useChatStreaming.ts</code>

确认：

- Context 有 token/size/step budget；
- 外部数据和 Tool output 有 untrusted/provenance 标签；
- Tool output 不能升级为 system instruction；
- Secret、完整 Prompt、raw exception 和 CoT 不进入普通日志、SSE、Memory 或 Eval；
- 大结果使用 Artifact/引用；
- Memory 写入显式、可审计、有 scope、confidence、来源和 retention/deletion 语义；
- 前端只展示 safe output，不把调试 payload 当作业务结果；
- SQL Memory 与 LangGraph Store 的重复路径有明确 owner 和兼容策略。

### 5.9 Model Gateway、Provider 和 SSRF

重点源码：

- <code>backend/app/harness/model_gateway.py</code>
- <code>backend/app/agents/provider_endpoint.py</code>
- <code>backend/app/agents/deepseek_chat_model.py</code>
- <code>backend/app/api/v1/agent.py</code>

确认：

- Provider 差异停留在 adapter/gateway；
- 业务层不判断具体供应商对象；
- streaming、usage、finish reason、latency 和 error 被归一化；
- usage unknown 不伪造为 0；
- model/version/provider 可追踪；
- BYOK 不被写入日志或模型上下文；
- provider endpoint 校验不能只依赖字面 IP，且 DNS、IPv6、redirect、私网和 metadata 访问有证据；
- 降级和重试不会放宽权限或安全策略。

### 5.10 Capability Registry、MCP 和 Allowlist

确认：

- Capability 有稳定名称、版本、输入/输出 Schema；
- metadata 明确 side effect、risk、timeout、retry、approval、permission 和 idempotency；
- 模型只看到当前 Agent 和用户允许的能力；
- 基础设施接口不直接暴露；
- MCP Exposure 与 HTTP/LangGraph 使用相同的 Policy、principal 和 safe result；
- 默认策略是 deny，未注册或未授权能力不会执行；
- registry 变更有 parity、negative authorization 和 result contract 测试。

### 5.11 Trace、Metrics 和 Eval

确认：

- run_id、trace_id、step_id、invocation_id、sequence 可关联；
- 记录 latency、status、retry、usage、provider、model 和 error category；
- redaction 默认开启且有测试；
- 关键 Policy、Approval、拒绝和副作用决定可审计；
- Eval 使用 fake provider/tool 时仍验证 Runtime、契约和恢复语义；
- 测试结果记录真实命令和退出码；
- 不稳定测试没有用无意义的 sleep 或降低断言掩盖。

## 6. 测试审查

Reviewer 必须确认测试确实运行并覆盖变更行为：

- 后端：<code>uv run --directory backend pytest</code> 或任务指定的精确子集；
- 后端 lint：<code>uv run --directory backend ruff check app tests</code>；
- 前端：<code>pnpm --dir frontend lint</code>、<code>typecheck</code>、<code>test</code>、必要时 <code>build</code>；
- Harness 任务：至少一个正常路径和一个失败/拒绝路径；
- 副作用：重复调用、payload conflict、timeout-after-success 和补偿；
- 取消：传播到下游并产生唯一 cancelled terminal event；
- 恢复：checkpoint、重启、replay 或明确的 abandoned 状态；
- 身份：匿名、跨用户、伪造 user_id 和资源越权 negative tests；
- 安全：prompt/tool output injection、SSRF、Secret redaction；
- 文档：链接、路径、命令和状态可由仓库检查。

测试只覆盖旧 adapter 而没有覆盖真实入口、只 mock 掉授权边界、只测试 200 响应而不确认副作用是否执行，均不能证明任务完成。

## 7. Diff 卫生和回滚

检查：

- Secret、Token、密码、BYOK、完整用户数据；
- .env、数据库、checkpoint、缓存、日志、.next、node_modules、.venv 和生成文件；
- 调试日志、raw provider payload 和 merge marker；
- 无关格式化和未解释依赖升级；
- 被删除的兼容层、失败测试或错误路径；
- 任务外源码、前端协议或数据库变更。

回滚方案必须说明：

- 如何关闭 feature flag 或恢复旧 adapter；
- 已持久化 Run/Event/Memory 是否保留；
- 外部 qB、日程、收藏、消息或文件状态如何人工核对；
- 回滚不会恢复匿名写入、绕过授权或重复执行副作用。

## 8. Review 输出格式

Reviewer 必须输出以下 YAML；file 和 symbol 是每个确定性 Finding 的必填证据：

~~~yaml
review_result:
  batch: BATCH-XX
  kind: batch | documentation
  verdict: pass | changes_required | blocked
  summary: 简要说明本次审查结论
  findings:
    - id: REVIEW-001
      severity: blocker | critical | high | medium | low
      category: correctness | security | architecture | compatibility | testing | scope | documentation | operations
      file: path/to/file
      symbol: symbol_name
      evidence: 具体代码行为、文档内容或命令结果
      impact: 可能造成的影响
      required_action: 必须采取的修复
  acceptance_checks:
    task_complete: true | false
    scope_compliant: true | false
    tests_verified: true | false
    architecture_compliant: true | false
    authorization_checked: true | false
    side_effects_checked: true | false
    recovery_checked: true | false
    compatibility_checked: true | false
    documentation_consistent: true | false
    rollback_available: true | false
  reviewed_commands:
    - command: ""
      exit_code: 0
  reviewed_files: []
  deferred_findings: []
~~~

## 9. Pass 标准

只有同时满足以下条件，verdict 才能为 pass：

- 当前任务目标完整实现，或文档任务的每个承诺已逐项核对；
- 修改范围合规；
- 相关命令真实执行且退出码符合预期；
- 不存在 Blocker、Critical 或 High；
- 不存在未处理的 Medium；
- Runtime、Decision、Policy、Authorization、副作用和恢复不变量没有被破坏；
- 公共 API、SSE、Tool、Schema 和配置兼容，或已有批准的迁移路径；
- 文档路径、源码事实、执行记录和审计结论一致；
- 回滚方式明确。

Review 规则不能替代自动化测试、CI、分支保护、用户审批、生产发布检查或外部系统状态核对。
