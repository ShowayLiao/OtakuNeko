# TASK-POST-AUDIT-012：ResultNormalizer、Schema 与 Safe Output Contract

## 目标

建立一次统一的 ResultNormalizer 边界，把 Capability、Tool、MCP、Workflow 和 Subagent 的原始返回转换为可持久化、可审计、可供模型和前端安全消费的 InvocationResult / RunEvent 投影。

目标数据流：

~~~text
model proposal
  -> DecisionParser
  -> Dispatcher input/schema/policy
  -> capability raw result
  -> ResultNormalizer
  -> canonical InvocationResult
  -> EventStore / model context / SSE / Trace projections
~~~

## 当前缺口

- Dispatcher 成功时仍可能直接保留 capability raw dict。
- Registry 的 input/output metadata、CapabilityResult 的 safe dict 和 SSE projection 尚未由一个唯一组件串联。
- Tool output、网页、RSS、MCP 和历史 Memory 默认是不可信数据，但模型上下文与 SSE 需要不同的安全投影。
- DecisionParser、Contract、CapabilityAdapter、MCP 对 runtime-owned authority fields 的拒绝集合不完全一致。

## 依赖与允许范围

### 依赖

- TASK-POST-AUDIT-006 的 Decision/Dispatcher contract。
- TASK-POST-AUDIT-011 的 ModelGateway error/cancellation contract。
- 可复用现有 ActionDescriptor、CapabilityResult、CapabilityRegistry、InvocationResult、RunEvent 和 trace redaction。

### 允许修改

- backend/app/harness/
- backend/app/capabilities/types.py
- backend/app/capabilities/registry.py
- backend/app/mcp_server/
- backend/app/api/v1/agent.py 的 projection 边界
- backend/tests/harness/
- backend/tests/acceptance/
- backend/tests/evaluation/
- 适用的前端 SSE contract tests
- 对应 execution record

### 禁止修改

- 不在本任务新增业务能力或改变 Domain Service 业务规则。
- 不以删除 raw output 测试、关闭 redaction 或降低 payload limit 的方式通过测试。
- 不把安全投影误当作领域结果；完整结果只能作为受控 artifact/reference 保存。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. Capability 输入不符合 input_schema 时，在执行前被拒绝，Domain Service 不被调用。
2. Capability 成功输出不符合 output_schema 时，Result 被标记为结构化 contract failure，不能伪造 succeeded。
3. 输出超过 payload、field、string 限制时被截断为明确的 bounded result 或 artifact reference，并保留审计信息。
4. raw provider payload、secret、token、完整 prompt、CoT 和未脱敏 exception 不进入 Event、Trace、SSE、Memory 或 Eval。
5. tool output 中的 prompt injection 只能作为 untrusted data 传递，不能修改 Policy、Approval、scope 或 Dispatcher 结果。
6. 模型上下文获得 model-safe output，前端获得 UI-safe output，canonical persistence 获得 audit-safe output；三者都能追溯同一个 invocation_id。
7. user_id、principal_id、tenant_id、role、scope、db、token、approval_state 等 runtime-owned fields 在所有入口使用同一拒绝规则。
8. 同一 invocation 的 decision_id、invocation_id、run_id、sequence 和 trace_id 关联稳定，重复投影不会生成第二个 invocation。

## 实现要求

### 1. 提取统一 authority field contract

定义唯一的 runtime-owned field 集合和递归检测方法，由 DecisionParser、Contract validators、Dispatcher、CapabilityAdapter、MCP adapter 和 schema projection 复用。Runtime 注入的字段不能通过 public/model arguments 覆盖。

### 2. 输入边界

Dispatcher 在 Capability execute 前按 Registry descriptor 进行：

- capability/version 校验；
- input schema 校验；
- argument bytes/depth/count 限制；
- authority field 拒绝；
- trusted context 注入；
- Policy、resource authorization、approval 和 idempotency 检查。

### 3. 输出边界

ResultNormalizer 必须产生至少包含以下字段的结构化结果：

~~~text
status
error_code/category
retryable
safe_output
artifacts/references
usage/latency
provenance
run_id
invocation_id
capability/version
~~~

原始结果不得直接成为模型消息、SSE payload 或普通 Event payload。

### 4. 三种 projection

- canonical persistence：保存可审计摘要、状态、哈希、引用和 redacted payload；
- model projection：只提供经过大小限制、来源标记和不可信标记的事实数据；
- UI/SSE projection：只提供前端所需安全字段，不泄漏 provider raw response、内部异常和凭据。

## 验收

- 新增 normalizer、schema、injection、oversize、redaction 和 ID correlation focused tests；
- 后端全量测试、Ruff、前端协议测试和适用 Eval 通过；
- canonical Event 不包含 raw prompt、CoT、secret 或完整 raw provider payload；
- ResultNormalizer 是 Dispatcher、MCP 和 SSE 的唯一结果归一化入口；
- Review verdict 为 pass，无未处理 High/Medium finding。

## 回滚

保留旧版本化 compatibility projection，但不得恢复 raw output 直通模型或前端。若某个旧消费者无法消费新 safe contract，使用显式版本适配器并记录迁移期限，不得降低统一 redaction、schema 和 payload 门禁。
