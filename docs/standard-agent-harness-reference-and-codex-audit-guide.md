# 标准 AI Agent Harness 参考架构与 Codex 审计指南

> 文档类型：参考架构 / 工程规范 / 代码审计基线  
> 适用项目：OtakuNeko 及其他具备 LLM、Tool Calling、Workflow、Subagent 的应用  
> 版本：1.0  
> 日期：2026-07-31  
> 状态：可作为重构 RFC 的上位规范  
> 规范关键词：**MUST / SHOULD / MAY** 分别表示“必须 / 应当 / 可选”

---

## 0. 文档目的

本文档定义一个**现代 AI Agent Harness 的项目无关参考架构**，用于指导 Codex 或其他代码 Agent：

1. 阅读现有仓库并识别 Agent 相关模块；
2. 将现有实现映射到标准 Harness 职责；
3. 找出职责缺失、耦合、重复和安全边界错误；
4. 生成可验证、可分批实施的重构方案；
5. 在不破坏现有业务功能的前提下，逐步演进为可维护的 Agent Runtime。

本文档不是某个框架的使用教程，也不要求项目必须改用 OpenAI Agents SDK、Google ADK、LangGraph 或 MCP。

本文所说的“标准 Harness”不是一个已被 ISO 或单一组织正式发布的统一标准，而是从主流 Agent Runtime、协议和工程实践中提炼出的**共同能力基线**。项目可以使用任意框架实现这些能力，但应保持本文定义的职责边界和运行语义。

---

## 1. Harness 的定义

### 1.1 定义

**Agent Harness** 是包围 LLM 的可信运行时系统。它负责把用户目标转换为受控的 Agent Run，并在模型、工具、数据、子 Agent、人工审批和外部系统之间建立可验证的执行闭环。

Harness 的核心不是 Prompt，而是：

- 控制执行循环；
- 构造和管理上下文；
- 解析模型提出的动作；
- 校验、授权并调度动作；
- 持久化运行状态；
- 处理重试、超时、取消和恢复；
- 记录可观测事件；
- 限制模型可以产生的外部影响。

### 1.2 最小运行闭环

```text
User / API
    ↓
Agent Runtime 创建 Run
    ↓
Context Compiler 构造模型上下文
    ↓
Model Gateway 调用 LLM
    ↓
LLM 返回 Decision / Action Proposal
    ↓
Runtime 解析、校验、授权
    ↓
执行 Tool / Capability / Workflow / Subagent
    ↓
返回结构化 InvocationResult
    ↓
Runtime 持久化状态并生成 Observation
    ↓
再次调用 LLM
    ↓
直到完成、失败、取消、暂停或超出预算
```

### 1.3 最重要的信任边界

```text
LLM = 非可信的动态决策来源
Runtime = 可信的执行控制面
Tool / Service = 受策略约束的执行数据面
```

LLM 可以**提出**调用工具、修改数据、委派任务或回答用户，但不能直接获得执行权。

因此：

- LLM **MUST NOT** 直接访问数据库连接、文件系统句柄、系统 Shell、用户凭据或任意网络客户端；
- Runtime **MUST** 对每个外部动作进行 Schema 校验和授权；
- Tool **MUST** 在服务端重新校验用户身份、资源归属和业务约束；
- Prompt 中的“禁止某行为”不能替代代码层面的权限控制。

---

## 2. 设计原则

### 2.1 Runtime 驱动，而非 LLM 驱动

Agent Runtime 是执行循环的唯一所有者。LLM 只返回下一步建议。

错误模型：

```text
LLM Orchestrator
    → 随意调用内部服务
    → 最后通知 Runtime
```

推荐模型：

```text
Runtime
    → 调用 LLM
    → 接收结构化 Decision
    → 校验 Decision
    → 调度受控执行
    → 记录 Result
    → 决定继续、暂停或终止
```

### 2.2 单一编排中心

项目 **SHOULD** 只有一个 Run 级别的控制中心。

以下职责不能分散在多个互不知情的模块中：

- 当前 Run 处于什么状态；
- 还可以调用多少次模型或工具；
- 哪个调用正在执行；
- 是否需要用户审批；
- 是否允许重试；
- 是否已经被取消；
- 最终回答是否已经提交。

业务 Workflow 可以拥有局部控制流，但不得绕过顶层 Runtime 的预算、策略、追踪和取消机制。

### 2.3 外部影响必须显式化

所有可能读取敏感数据或产生副作用的动作都 **MUST** 被建模为显式 Invocation，例如：

- ToolInvocation；
- CapabilityInvocation；
- WorkflowInvocation；
- AgentDelegation；
- HumanApprovalRequest。

不得在 Prompt 构造器、格式化器、记忆检索器或结果渲染器中隐藏写数据库、发消息、下载文件等副作用。

### 2.4 结构化契约优先

模型输出、工具输入、工具输出、运行状态和事件都 **SHOULD** 使用版本化 Schema。

禁止把以下内容当作唯一接口：

```python
result = "成功了，大概写入了三条记录"
```

应返回：

```json
{
  "schema_version": "1.0",
  "status": "succeeded",
  "output": {
    "created_count": 3,
    "resource_ids": ["a", "b", "c"]
  }
}
```

### 2.5 可恢复执行

生产级 Harness **SHOULD** 能在以下场景恢复：

- 服务进程重启；
- 模型调用暂时失败；
- 工具调用超时；
- 用户稍后批准敏感操作；
- 长任务暂停；
- 流式连接断开；
- 子 Agent 执行时间较长。

恢复不能依赖 Python 内存中的闭包、对象引用或未持久化消息列表。

### 2.6 最小权限与最小代理权

每个 Agent、Tool 和 Run 只应获得完成当前任务所需的最小权限：

- 可使用的工具集合；
- 可访问的数据范围；
- 可执行的动作类型；
- 允许的网络域名；
- 最大资源消耗；
- 是否允许产生外部副作用；
- 是否需要人工确认。

### 2.7 Provider 与业务解耦

业务逻辑 **MUST NOT** 依赖某个模型供应商的原始响应对象。

应通过 `ModelGateway` 归一化：

- Messages；
- Tool definitions；
- Structured output；
- Streaming events；
- Token usage；
- Finish reason；
- Error taxonomy。

### 2.8 可观测、可评估、可回归

任何“Agent 看起来能用”的实现都不够。Harness **MUST** 能回答：

- 为什么调用了这个工具？
- 使用了哪些上下文？
- 工具输入和输出是什么？
- 哪条策略允许或阻止了调用？
- 运行在哪一步失败？
- 消耗了多少 token、时间和费用？
- 新版本是否使任务成功率下降？
- 是否产生重复副作用？

---

## 3. 参考架构

```text
┌─────────────────────────────────────────────────────────────┐
│                        Ingress Layer                         │
│  HTTP / WebSocket / SSE / CLI / Scheduled Job / Webhook    │
└──────────────────────────────┬──────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                     Agent Runtime / Harness                  │
│                                                             │
│  Run Coordinator        Lifecycle State Machine             │
│  Context Compiler       Model Gateway                       │
│  Decision Parser        Policy & Guardrail Engine           │
│  Capability Registry    Invocation Dispatcher               │
│  Budget Manager         Cancellation Controller             │
│  Retry Controller       Result Normalizer                   │
└───────────────┬───────────────────────┬─────────────────────┘
                │                       │
                ↓                       ↓
┌──────────────────────────┐  ┌───────────────────────────────┐
│      Execution Plane     │  │        Persistence Plane      │
│                          │  │                               │
│ Tool / Capability        │  │ Run Store                     │
│ Workflow                 │  │ Event Store                   │
│ Subagent                 │  │ Checkpoint Store              │
│ MCP Client               │  │ Artifact Store                │
│ Human Approval           │  │ Memory Store                  │
│ Sandbox                  │  │ Idempotency Store             │
└───────────────┬──────────┘  └───────────────────────────────┘
                ↓
┌─────────────────────────────────────────────────────────────┐
│             Domain Services and External Systems            │
│ DB / Search / Bangumi / Calendar / qBittorrent / APIs      │
└─────────────────────────────────────────────────────────────┘

Cross-cutting:
Authentication / Authorization / Secrets / Audit / Tracing /
Metrics / Evaluation / Rate Limits / Cost Controls / Privacy
```

---

## 4. 核心组件职责

## 4.1 Ingress Layer

Ingress 将外部请求转换为规范化的 `RunRequest`。

它可以接收：

- HTTP 请求；
- SSE 或 WebSocket 对话；
- CLI 命令；
- 定时任务；
- 队列消息；
- 外部事件。

Ingress **MUST**：

- 完成用户认证；
- 生成或接收 `request_id`；
- 解析租户、用户、会话和角色；
- 传递取消信号；
- 不直接调用 Tool；
- 不在 Controller 中实现 Agent Loop。

建议契约：

```python
class RunRequest:
    request_id: str
    user_id: str
    tenant_id: str | None
    session_id: str | None
    agent_id: str
    input: list["InputItem"]
    requested_capabilities: list[str] | None
    metadata: dict[str, object]
```

## 4.2 Run Coordinator

`RunCoordinator` 是一次 Agent Run 的唯一控制者。

它 **MUST** 负责：

- 创建 Run；
- 加载 Agent 配置；
- 推进状态机；
- 控制最大步数；
- 调用 Context Compiler；
- 调用 Model Gateway；
- 处理 Decision；
- 调度 Invocation；
- 写入 Checkpoint；
- 处理暂停、恢复、取消和终止；
- 生成最终 `RunResult`。

它 **MUST NOT**：

- 实现 Bangumi、数据库或其他业务逻辑；
- 拼接供应商专属的请求体；
- 将所有职责塞进一个数千行函数；
- 依赖 HTTP 连接一直存在才能完成 Run。

## 4.3 Context Compiler

Context 不是简单的聊天消息列表，而是一个受预算约束的编译产物。

Context Compiler 的输入可能包括：

- Agent 指令；
- 当前用户输入；
- 会话消息；
- Run 状态；
- Tool 描述；
- 用户画像；
- 检索结果；
- Memory；
- Artifact 引用；
- 子 Agent 返回；
- 系统时间；
- 策略提示；
- 历史摘要。

Context Compiler **MUST**：

- 明确各来源的优先级和信任等级；
- 控制 token 预算；
- 对旧消息做截断或摘要；
- 避免把秘密、内部策略和无关数据发给模型；
- 记录本轮实际选入的 Context Item；
- 支持复现实验时重新构造等价上下文。

建议模型：

```python
class ContextItem:
    id: str
    kind: str
    source: str
    trust_level: str
    content: object
    token_estimate: int
    sensitivity: str
    created_at: datetime
```

### Context 与 Memory 的区别

- **Context**：本次模型调用实际看见的内容；
- **Session State**：当前会话中需要持续维护的结构化状态；
- **Memory**：跨轮次或跨会话可检索的信息；
- **Artifact**：不适合直接塞入消息的文件或二进制对象；
- **Event History**：不可变的运行事实记录。

不得把这五者合并成一个无限增长的 `messages` 字段。

## 4.4 Model Gateway

`ModelGateway` 对不同模型供应商提供统一接口。

它 **SHOULD** 支持：

- 模型路由；
- 结构化输出；
- Tool Calling；
- Streaming；
- 超时；
- 供应商级重试；
- 使用量归一化；
- 模型错误归一化；
- 模型版本固定；
- 降级策略；
- 可选的缓存。

建议接口：

```python
class ModelGateway(Protocol):
    async def generate(
        self,
        request: "ModelRequest",
        cancellation: "CancellationToken",
    ) -> "ModelResponse":
        ...
```

禁止上层业务代码判断诸如：

```python
if provider == "deepseek":
    ...
elif provider == "openai":
    ...
```

供应商差异应被限制在 Adapter 内。

## 4.5 Decision Parser

模型响应应被归一化为有限集合中的 `AgentDecision`。

```python
AgentDecision =
    FinalAnswer
    | InvokeCapability
    | DelegateAgent
    | RequestUserInput
    | RequestApproval
    | NoOp
```

Parser **MUST**：

- 校验结构；
- 拒绝未知 Decision 类型；
- 处理不完整参数；
- 保留模型原始响应的引用；
- 不执行任何外部动作。

示例：

```json
{
  "schema_version": "1.0",
  "decision_id": "dec_123",
  "type": "invoke_capability",
  "capability": "anime.search",
  "arguments": {
    "query": "赛博朋克 动画"
  },
  "reason_summary": "需要查找候选条目后再回答"
}
```

`reason_summary` 只能作为审计辅助，不能作为授权依据。

## 4.6 Policy 与 Guardrail Engine

策略引擎位于模型和执行器之间。

它 **MUST** 检查：

- Agent 是否被允许使用该 Capability；
- 当前用户是否有资源权限；
- 参数是否符合 Schema；
- 是否超过 Run 预算；
- 是否要求人工确认；
- 是否包含禁止的域名、路径、命令或数据范围；
- 是否违反租户隔离；
- 是否存在已知高风险组合调用；
- 是否满足业务前置条件。

Guardrail 分层：

```text
Input Guardrail
    检查用户输入和附件

Decision Guardrail
    检查模型提出的动作

Tool Input Guardrail
    检查工具参数

Tool Output Guardrail
    检查返回数据、注入内容和敏感信息

Final Output Guardrail
    检查最终对用户输出
```

策略结果必须结构化：

```python
class PolicyDecision:
    effect: Literal["allow", "deny", "require_approval"]
    policy_ids: list[str]
    reason_code: str
    safe_message: str | None
```

## 4.7 Capability Registry

Registry 是所有可调用能力的权威目录。

一个 Capability 定义至少包含：

```python
class CapabilityDefinition:
    name: str
    version: str
    description: str
    input_schema: dict
    output_schema: dict
    side_effect: Literal["none", "read", "write", "external"]
    risk_level: Literal["low", "medium", "high", "critical"]
    idempotency: Literal["required", "supported", "none"]
    timeout_seconds: int
    retry_policy: str
    required_permissions: list[str]
    approval_policy: str | None
    implementation_ref: str
```

Registry **SHOULD** 支持：

- 版本管理；
- 启用和禁用；
- Agent 级白名单；
- 动态发现；
- MCP Tool 映射；
- Schema 校验；
- 健康检查；
- 元数据缓存。

模型能看到的 Tool 描述应由 Registry 和 Policy 联合裁剪，而不是把所有工具无条件暴露给所有 Agent。

## 4.8 Invocation Dispatcher

Dispatcher 将已授权的 Invocation 路由到实际执行器。

支持目标：

- 本地函数；
- Domain Service；
- HTTP 服务；
- MCP Server；
- Workflow；
- Subagent；
- Sandbox；
- 人工审批队列。

Dispatcher **MUST**：

- 创建 `invocation_id`；
- 传播 Trace Context；
- 传播用户和租户身份；
- 应用超时；
- 处理取消；
- 应用并发限制；
- 记录开始与结束事件；
- 将异常归一化；
- 支持幂等键；
- 不把未经处理的异常堆栈直接返回给模型或用户。

## 4.9 Result Normalizer

所有执行目标应返回统一外壳：

```python
class InvocationResult:
    schema_version: str
    invocation_id: str
    invocation_type: Literal[
        "tool", "capability", "workflow", "agent", "human"
    ]
    status: Literal[
        "succeeded", "failed", "cancelled",
        "timed_out", "suspended", "partial"
    ]
    output: object | None
    error: "InvocationError | None"
    artifacts: list["ArtifactRef"]
    usage: "Usage"
    metadata: dict[str, object]
```

错误模型：

```python
class InvocationError:
    code: str
    category: Literal[
        "validation", "authorization", "dependency",
        "timeout", "rate_limit", "conflict",
        "not_found", "internal", "cancelled"
    ]
    message: str
    retryable: bool
    retry_after_ms: int | None
    safe_for_model: bool
```

原始 HTML、超长 JSON 或数据库对象 **SHOULD NOT** 直接回传给模型。Result Normalizer 应：

- 截断；
- 摘要；
- 脱敏；
- 提取关键字段；
- 将大对象保存为 Artifact；
- 保留原始结果引用用于审计。

---

## 5. Tool、Capability、Skill、Workflow 与 Subagent

这些概念可以共享统一 Invocation 外壳，但不能混为一谈。

| 类型 | 主要语义 | 是否有独立循环 | 是否通常有副作用 | 典型用途 |
|---|---|---:|---:|---|
| Tool | 单次可调用操作 | 否 | 可能 | 查询条目、写入日历 |
| Capability | 面向 Agent 的稳定能力契约 | 否或内部隐藏 | 可能 | `anime.search`、`profile.generate` |
| Skill | 指令、资源、脚本和流程知识的可复用包 | 通常否 | 取决于内部 Tool | 代码审查、报告生成 |
| Workflow | 显式、可预测的多步控制流 | 可有局部循环 | 可能 | 同步收藏、生成年度报告 |
| Subagent | 具有独立模型上下文和执行循环的 Agent | 是 | 通过其工具产生 | 研究、规划、代码审计 |
| MCP Server | 暴露 Tool、Resource、Prompt 的协议服务 | 不一定 | 可能 | 外部能力接入 |

### 5.1 Tool 不应承载完整 Agent

如果一个 Tool 内部再次自由调用 LLM、反复使用工具并维护长状态，它实际上是 Workflow 或 Subagent，应显式建模。

### 5.2 Capability 应屏蔽基础设施细节

模型应看到：

```text
anime.search
collection.list
schedule.create
```

而不是：

```text
sqlalchemy_execute_raw_sql
http_get_bangumi_url
redis_hgetall
```

Capability 是面向任务的稳定语义；基础设施 API 是实现细节。

### 5.3 Subagent 委派契约

委派不能只传一段自然语言。

推荐请求：

```python
class DelegationRequest:
    delegation_id: str
    parent_run_id: str
    target_agent_id: str
    objective: str
    scope: list[str]
    constraints: list[str]
    expected_output_schema: dict
    capability_allowlist: list[str]
    budget: "RunBudget"
    context_refs: list[str]
```

推荐结果：

```python
class AgentResult:
    status: Literal["succeeded", "failed", "partial", "cancelled"]
    summary: str
    structured_output: object | None
    evidence: list["EvidenceRef"]
    artifacts: list["ArtifactRef"]
    unresolved_items: list[str]
    usage: "Usage"
```

父 Agent **MUST NOT** 默认继承子 Agent 的全部上下文；子 Agent **MUST NOT** 默认继承父 Agent 的全部权限。

---

## 6. Agent Run 生命周期

### 6.1 状态机

```text
CREATED
  ↓
QUEUED
  ↓
RUNNING
  ├── WAITING_MODEL
  ├── WAITING_TOOL
  ├── WAITING_SUBAGENT
  ├── WAITING_APPROVAL
  ├── WAITING_USER
  ├── RETRY_SCHEDULED
  └── SUSPENDED
  ↓
COMPLETED | FAILED | CANCELLED | EXPIRED
```

状态转换 **MUST**：

- 由 Runtime 执行；
- 写入 Event Store；
- 校验合法性；
- 带有版本号或乐观锁；
- 支持幂等重放。

### 6.2 终止条件

Run 至少应支持以下终止条件：

- 模型产生可接受的 FinalAnswer；
- 达到最大模型调用次数；
- 达到最大工具调用次数；
- 达到最大总步骤数；
- 超过 token 预算；
- 超过费用预算；
- 超过墙钟时间；
- 用户取消；
- 策略拒绝；
- 不可重试错误；
- 重复动作检测；
- 无进展循环检测。

### 6.3 推荐执行伪代码

```python
async def run_agent(request: RunRequest) -> RunResult:
    run = await run_store.create(request)

    while not run.is_terminal:
        await cancellation.raise_if_cancelled(run.id)
        await budget.ensure_available(run.id)

        checkpoint = await checkpoint_store.save(run)

        context = await context_compiler.build(run)
        await event_store.append(ContextBuilt.from_context(context))

        model_response = await model_gateway.generate(
            ModelRequest.from_context(context),
            cancellation=run.cancellation_token,
        )

        decision = decision_parser.parse(model_response)
        policy = await policy_engine.evaluate(run, decision)

        if policy.effect == "deny":
            run = await run.fail(policy.reason_code)
            continue

        if policy.effect == "require_approval":
            run = await run.suspend_for_approval(decision, policy)
            continue

        match decision:
            case FinalAnswer():
                final = await final_output_guardrail.check(decision)
                run = await run.complete(final)

            case InvokeCapability():
                result = await dispatcher.invoke(run, decision)
                observation = await result_normalizer.to_observation(result)
                run = await run.append_observation(observation)

            case DelegateAgent():
                result = await dispatcher.delegate(run, decision)
                run = await run.append_observation(
                    await result_normalizer.to_observation(result)
                )

            case RequestUserInput():
                run = await run.suspend_for_user(decision)

            case _:
                run = await run.fail("unsupported_decision")

    return await run_store.get_result(run.id)
```

---

## 7. 持久化模型

### 7.1 必需实体

生产级实现建议至少具备：

#### AgentDefinition

- `agent_id`
- `version`
- `instructions_ref`
- `model_policy`
- `capability_policy`
- `context_policy`
- `budget_policy`
- `guardrail_policy`
- `output_schema`
- `enabled`

#### Session

- `session_id`
- `user_id`
- `tenant_id`
- `created_at`
- `updated_at`
- `state`
- `summary`
- `version`

#### Run

- `run_id`
- `session_id`
- `agent_id`
- `agent_version`
- `status`
- `current_step`
- `budget_snapshot`
- `started_at`
- `completed_at`
- `error_code`
- `version`

#### RunStep

- `step_id`
- `run_id`
- `sequence`
- `step_type`
- `status`
- `input_ref`
- `output_ref`
- `started_at`
- `completed_at`

#### Invocation

- `invocation_id`
- `run_id`
- `step_id`
- `target_type`
- `target_name`
- `target_version`
- `arguments`
- `status`
- `idempotency_key`
- `policy_decision_ref`
- `result_ref`

#### Event

- `event_id`
- `run_id`
- `sequence`
- `event_type`
- `payload`
- `created_at`
- `trace_id`

#### Checkpoint

- `checkpoint_id`
- `run_id`
- `sequence`
- `state`
- `created_at`
- `schema_version`

#### Artifact

- `artifact_id`
- `owner_type`
- `owner_id`
- `media_type`
- `storage_uri`
- `checksum`
- `size`
- `version`
- `sensitivity`

#### Approval

- `approval_id`
- `run_id`
- `invocation_id`
- `status`
- `requested_from`
- `decision_by`
- `expires_at`
- `reason`

### 7.2 Event 与 State

推荐采用：

```text
Event = 不可变的事实
State = 由事件演化而来的当前快照
Checkpoint = 可恢复执行所需的完整或增量快照
```

不要求完整 Event Sourcing，但不应只保存最终聊天消息而丢失运行过程。

### 7.3 幂等性

有副作用的操作 **MUST** 考虑幂等性，例如：

- 创建日历事件；
- 写入收藏；
- 发消息；
- 添加下载任务；
- 扣费；
- 创建外部工单。

幂等键建议由以下字段构成：

```text
tenant_id + user_id + run_id + logical_action_id + capability_version
```

重试前必须判断上一次调用是否可能已经成功。

---

## 8. Streaming 与前端事件

SSE 或 WebSocket 是展示通道，不应成为内部运行状态的唯一载体。

推荐事件：

```text
run.created
run.started
context.built
model.started
model.delta
model.completed
decision.created
policy.evaluated
invocation.started
invocation.progress
invocation.completed
approval.requested
run.suspended
run.resumed
final.delta
run.completed
run.failed
run.cancelled
```

每个事件建议包含：

```json
{
  "schema_version": "1.0",
  "event_id": "evt_123",
  "run_id": "run_123",
  "sequence": 12,
  "type": "invocation.completed",
  "timestamp": "2026-07-31T12:00:00Z",
  "trace_id": "trace_123",
  "payload": {}
}
```

前端断线后应能通过 `run_id + last_sequence` 补拉事件，而不是强制重新执行任务。

模型 Token Streaming 与 Run Event Streaming 应逻辑分离：

- Token delta 用于 UI 实时显示；
- Run event 用于状态同步、恢复和审计。

---

## 9. 错误、重试、超时与取消

### 9.1 错误分类

错误至少分为：

- ValidationError；
- AuthenticationError；
- AuthorizationError；
- PolicyDenied；
- DependencyUnavailable；
- RateLimited；
- Timeout；
- Conflict；
- NotFound；
- ModelError；
- ToolError；
- InternalError；
- Cancelled。

禁止所有异常都转换成：

```text
工具调用失败，请重试
```

### 9.2 重试原则

只对明确可重试的错误重试：

- 网络瞬断；
- 供应商 429；
- 可恢复的 5xx；
- 临时锁冲突；
- 明确声明为 retryable 的依赖错误。

以下情况通常不应自动重试：

- 参数校验失败；
- 权限不足；
- 策略拒绝；
- 资源不存在；
- 非幂等写操作结果未知；
- 相同输入连续产生相同逻辑错误。

重试策略应包括：

- 最大次数；
- 指数退避；
- 抖动；
- 总时间上限；
- `Retry-After`；
- 熔断；
- 幂等检查。

### 9.3 超时层级

建议分别定义：

- Model call timeout；
- Tool call timeout；
- Subagent timeout；
- Step timeout；
- Run timeout；
- Queue wait timeout；
- Approval expiration。

### 9.4 取消

取消信号应从用户入口传播到：

```text
Ingress
  → Run Coordinator
  → Model Gateway
  → Dispatcher
  → Tool / Workflow / Subagent
```

Tool 应定期检查取消信号。无法中断的外部调用应在结束后丢弃过期结果，并避免继续推进已取消的 Run。

---

## 10. 安全基线

### 10.1 身份传播

每个 Invocation 都应携带不可由模型伪造的执行身份：

```python
class ExecutionPrincipal:
    user_id: str
    tenant_id: str | None
    roles: list[str]
    scopes: list[str]
    auth_context_ref: str
```

身份信息由 Runtime 注入，不能来自模型参数。

### 10.2 Tool 级授权

即使 Runtime 已授权，Tool 或 Domain Service 也必须重新执行资源级授权。

例如模型调用：

```json
{
  "capability": "collection.delete",
  "arguments": {"collection_id": "123"}
}
```

服务端必须验证 `collection_id=123` 是否属于当前用户，而不是相信模型选择的 ID。

### 10.3 Prompt Injection 防护

外部数据、网页、数据库文本和 Tool Result 都应视为不可信内容。

推荐措施：

- 标注来源和信任等级；
- 将外部内容与系统指令分离；
- 不把 Tool Result 当作高优先级指令；
- 限制工具集合；
- 对高风险调用二次确认；
- 对 Tool Output 做注入检测或安全归一化；
- 禁止外部内容修改 Runtime Policy；
- 防止检索内容诱导读取秘密或调用未授权工具。

### 10.4 Secrets

- Secret **MUST NOT** 出现在模型上下文；
- Secret **MUST NOT** 写入普通事件日志；
- Tool 应接收 Secret 引用或由执行环境注入；
- BYOK 场景应使用加密存储；
- 日志和 Trace 必须脱敏；
- 不得由模型决定使用哪个用户的凭据。

### 10.5 Sandbox

执行代码、Shell、浏览器自动化或不可信插件时应使用隔离环境，并限制：

- 文件系统；
- 网络；
- CPU；
- 内存；
- 执行时间；
- 进程；
- 环境变量；
- 系统调用；
- 持久化目录。

### 10.6 Human-in-the-loop

以下动作通常应支持审批：

- 删除或覆盖数据；
- 发送外部消息；
- 产生费用；
- 公开发布内容；
- 启动下载或外部任务；
- 修改账户、安全或权限配置；
- 执行任意代码；
- 高影响批量操作。

审批请求必须展示最终参数，而不是只展示模糊描述。

---

## 11. Context、Memory 与数据治理

### 11.1 Memory 类型

建议区分：

- Working Memory：当前 Run 的临时结构化状态；
- Session Memory：当前会话的摘要和偏好；
- Episodic Memory：历史交互事件；
- Semantic Memory：可检索知识；
- Profile Memory：用户明确或推断的长期偏好；
- Procedural Memory：Skill、规则和操作方法。

### 11.2 写入 Memory 的规则

Memory 写入 **SHOULD** 是显式动作，并记录：

- 来源；
- 置信度；
- 写入原因；
- 作用域；
- 过期时间；
- 敏感级别；
- 是否经过用户确认；
- 可删除性。

模型不能把任何一句对话都自动视为永久事实。

### 11.3 数据删除

删除用户数据时，需要考虑：

- Session；
- Memory；
- Artifact；
- Trace；
- Evaluation Dataset；
- Cache；
- Vector Index；
- Backups；
- 外部服务副本。

---

## 12. 可观测性

### 12.1 Trace 层级

推荐 Trace 结构：

```text
Agent Run Span
  ├── Context Build Span
  ├── Model Call Span
  ├── Decision Parse Span
  ├── Policy Evaluation Span
  ├── Tool Invocation Span
  ├── Subagent Span
  └── Finalization Span
```

### 12.2 必要字段

建议记录：

- `trace_id`
- `run_id`
- `session_id`
- `agent_id`
- `agent_version`
- `model_provider`
- `model_name`
- `model_version`
- `capability_name`
- `capability_version`
- `step_index`
- latency
- input/output token
- cached token
- estimated cost
- retry count
- status
- error code
- policy decision
- approval status

不得默认记录完整敏感 Prompt、Tool 参数和 Tool 输出。应支持采样、脱敏和字段级关闭。

### 12.3 指标

至少应有：

- Run 成功率；
- 任务成功率；
- 平均步骤数；
- 模型调用次数；
- 工具调用成功率；
- P50/P95/P99 延迟；
- Token 与费用；
- 重试率；
- 超时率；
- 人工审批率；
- 取消率；
- 循环终止率；
- 重复副作用拦截数；
- 各 Capability 错误分布。

---

## 13. Evaluation 与测试

### 13.1 测试金字塔

#### 单元测试

- Decision Parser；
- Policy；
- Schema；
- Result Normalizer；
- Context Selection；
- Budget；
- State Transition；
- Retry；
- Idempotency。

#### 契约测试

- Tool 输入输出 Schema；
- MCP Tool 映射；
- Model Adapter；
- Event Schema；
- SSE 消费协议；
- Subagent 结果协议。

#### 集成测试

- Runtime + 假模型；
- Runtime + 假工具；
- Checkpoint 恢复；
- 用户审批恢复；
- 断线重连；
- 取消传播；
- 数据库事务。

#### 端到端测试

- 真实用户任务；
- 多轮 Tool Calling；
- 错误恢复；
- 权限隔离；
- 高风险动作审批；
- 多模型兼容。

#### 安全测试

- Prompt Injection；
- Tool Output Injection；
- 越权资源访问；
- 目录穿越；
- SSRF；
- Secret 泄露；
- 恶意 Subagent；
- Memory Poisoning；
- 重放和重复写入。

### 13.2 Agent Evaluation 维度

不能只评估最终文案。建议评估：

- Task Success；
- Factual Correctness；
- Tool Selection；
- Tool Argument Correctness；
- Policy Compliance；
- Side-effect Correctness；
- Step Efficiency；
- Recovery Capability；
- Citation / Evidence Quality；
- User Experience；
- Cost；
- Latency。

### 13.3 回归门槛

每次修改以下内容时应运行 Eval：

- System Prompt；
- Tool 描述；
- Tool Schema；
- 模型；
- 模型参数；
- Context 裁剪；
- Memory；
- Agent Loop；
- Policy；
- Subagent 委派规则。

应固定模型版本或记录确切版本，以便解释回归。

---

## 14. 配置与版本管理

以下对象应有明确版本：

- AgentDefinition；
- Prompt；
- Capability；
- Tool Schema；
- Workflow；
- Policy；
- Context Policy；
- Model Policy；
- Event Schema；
- Checkpoint Schema；
- Evaluation Dataset。

每个 Run 应保存配置快照或不可变引用，使历史运行可解释。

推荐配置：

```yaml
agent:
  id: otakuneko.chat
  version: 2.0.0
  model_policy: chat-default-v3
  context_policy: chat-context-v2
  capability_policy: anime-readonly-v1
  guardrail_policy: consumer-assistant-v1
  budget_policy: interactive-v1
  output_schema: chat-response-v1
```

---

## 15. 推荐代码边界

以下目录仅表示职责，不要求机械照搬：

```text
backend/app/agent_harness/
├── api/
│   ├── run_routes.py
│   └── stream_routes.py
├── runtime/
│   ├── coordinator.py
│   ├── lifecycle.py
│   ├── budget.py
│   ├── cancellation.py
│   └── retry.py
├── context/
│   ├── compiler.py
│   ├── selectors.py
│   ├── summarizer.py
│   └── policies.py
├── model/
│   ├── gateway.py
│   ├── types.py
│   └── adapters/
├── decision/
│   ├── models.py
│   └── parser.py
├── policy/
│   ├── engine.py
│   ├── authorization.py
│   ├── approvals.py
│   └── guardrails.py
├── capabilities/
│   ├── registry.py
│   ├── definitions.py
│   ├── dispatcher.py
│   └── adapters/
├── agents/
│   ├── registry.py
│   ├── delegation.py
│   └── definitions/
├── persistence/
│   ├── run_store.py
│   ├── event_store.py
│   ├── checkpoint_store.py
│   ├── artifact_store.py
│   └── memory_store.py
├── observability/
│   ├── tracing.py
│   ├── metrics.py
│   └── audit.py
├── evals/
│   ├── datasets/
│   ├── graders/
│   └── runners/
└── contracts/
    ├── events.py
    ├── invocations.py
    ├── results.py
    └── versions.py
```

业务服务保持在 Harness 外部：

```text
backend/app/domain/
backend/app/services/
backend/app/integrations/
```

Harness 调用 Domain Service，Domain Service 不应依赖具体 LLM 框架。

---

## 16. 常见反模式

### 16.1 巨型 Agent 文件

特征：

- Prompt、LLM 初始化、Tool 定义、数据库查询、SSE、重试都在一个文件；
- 全局变量保存会话；
- 修改一个 Tool 会影响整个运行循环。

整改：按 Runtime、Model、Capability、Policy、Persistence 分离。

### 16.2 Tool 直接暴露 ORM

特征：

- Tool 直接接收任意 SQL；
- Tool 返回 ORM 对象；
- 模型可以指定 `user_id`；
- 没有资源级授权。

整改：使用面向领域的 Capability，并在服务端绑定当前用户。

### 16.3 把 LangGraph 当作全部 Harness

LangGraph 可以承担 Workflow/Runtime 的一部分，但项目仍需明确：

- Policy；
- Capability Registry；
- 身份传播；
- Tool 契约；
- Artifact；
- Eval；
- 配置版本；
- 安全审计。

框架对象本身不等于完整工程架构。

### 16.4 只保存聊天消息

特征：

- 无法知道调用过哪些工具；
- 服务重启后任务丢失；
- 无法恢复审批；
- 无法定位重复写入。

整改：保存 Run、Step、Invocation、Event 和 Checkpoint。

### 16.5 Tool Error 直接变成 Prompt 文本

特征：

- 异常堆栈进入模型上下文；
- 模型根据不稳定字符串判断是否重试；
- 敏感路径或凭据泄漏。

整改：归一化为结构化、安全的错误对象。

### 16.6 所有工具对所有 Agent 可见

特征：

- 模型经常误选工具；
- Prompt Injection 可调用高风险能力；
- Tool 描述占用大量 Context。

整改：按 Agent、用户、任务和状态动态生成 Allowlist。

### 16.7 HTTP 断开等于 Run 取消或丢失

整改：Run 独立持久化；SSE 只是订阅事件。

### 16.8 用自然语言实现权限

例如 Prompt 写着“不要删除用户数据”。这不构成安全控制。

整改：Policy Engine + Domain Authorization + Approval。

### 16.9 无界循环

特征：

- ReAct 一直调用工具；
- 相同参数重复调用；
- Token 和费用失控。

整改：步数、预算、重复检测、无进展检测和 Run Deadline。

### 16.10 直接重构成“大而全平台”

整改应采用增量替换。先建立契约和观测，再迁移执行路径。

---

## 17. Harness 成熟度模型

### Level 0：LLM Wrapper

- 单次 LLM 调用；
- 无工具或仅手写函数调用；
- 无 Run 状态；
- 无结构化事件。

### Level 1：Agent Loop

- 模型可调用工具；
- Tool Result 回传模型；
- 有最大步数；
- 主要状态仍在内存。

### Level 2：Controlled Runtime

- 统一 Decision 与 Invocation；
- Tool Registry；
- Schema 校验；
- 超时、重试和取消；
- 基本 Trace；
- 权限白名单。

### Level 3：Durable Harness

- Run/Step/Event/Checkpoint 持久化；
- 可暂停恢复；
- Human-in-the-loop；
- Artifact；
- 幂等；
- 流式断线恢复。

### Level 4：Production Agent Platform

- 多 Agent 和 Workflow；
- 细粒度 Policy；
- 全链路身份传播；
- Eval 门禁；
- 成本和 SLO；
- 多租户隔离；
- 安全测试；
- 动态 Capability；
- 版本化配置。

### Level 5：Adaptive Platform

- 基于任务动态路由 Agent 和模型；
- 自动 Eval 与回归诊断；
- 策略驱动的长期任务；
- 风险自适应审批；
- 完整治理和审计。

项目不需要立即达到 Level 5。个人或早期项目通常先以可靠的 Level 2 为目标，再演进到 Level 3。

---

# 第二部分：Codex 仓库审计规范

## 18. Codex 审计目标

Codex 的首轮任务不是立即改代码，而是建立**源码事实模型**。

审计必须回答：

1. 当前 Agent Run 从哪个入口创建？
2. 谁拥有运行循环？
3. 模型调用在哪里？
4. Tool 如何注册、选择和执行？
5. 用户身份如何传播到 Tool？
6. 状态保存在哪里？
7. 服务重启后能否恢复？
8. SSE 断开时发生什么？
9. 有哪些副作用操作？
10. 哪些操作具备幂等性？
11. 是否存在重复编排中心？
12. 是否有跨层依赖或循环依赖？
13. 错误如何分类和传播？
14. 预算、超时、重试和取消在哪里控制？
15. 是否存在测试和 Eval？
16. 哪些 README 描述与源码不一致？

## 19. 证据规则

Codex 的每个结论都必须包含：

- 文件路径；
- 类、函数或符号；
- 必要时给出行号；
- 代码行为摘要；
- 对应本文规范条款；
- 置信度；
- 未确认项。

禁止：

- 只根据文件名推断实现；
- 只根据 README 判断；
- 没有找到代码就声称“不存在”；
- 把计划中功能当作已实现；
- 将框架默认能力当作项目已经正确配置；
- 为了符合目标架构而虚构现有模块。

示例：

```markdown
### GAP-RUNTIME-003：Run 生命周期仅存在于 HTTP 请求内

- 严重度：P1
- 证据：
  - `backend/app/api/chat.py::stream_chat`
  - `backend/app/agent/graph.py::invoke_agent`
- 当前行为：
  - Run 状态保存在局部变量；
  - SSE 断开后没有持久化恢复路径。
- 对照条款：
  - §6 Agent Run 生命周期
  - §8 Streaming 与前端事件
- 风险：
  - 网络断开导致任务不可恢复；
  - 无法区分客户端断线和用户取消。
- 建议：
  - 引入 Run Store 与 Event Store；
  - 将 SSE 改为订阅持久化 Run 事件。
- 置信度：高
```

## 20. 审计输出物

Codex 首轮应生成以下文件，不修改业务代码：

```text
docs/harness-audit/
├── 00-executive-summary.md
├── 01-current-architecture.md
├── 02-runtime-flow.md
├── 03-capability-inventory.md
├── 04-state-and-persistence.md
├── 05-security-boundaries.md
├── 06-observability-and-evals.md
├── 07-gap-analysis.md
├── 08-target-architecture.md
├── 09-migration-plan.md
├── 10-risk-register.md
└── 11-task-backlog.md
```

### 20.1 `00-executive-summary.md`

包括：

- 当前成熟度等级；
- 最高风险 5 项；
- 最值得保留的现有设计；
- 推荐目标等级；
- 预计重构批次；
- 不建议立刻修改的区域。

### 20.2 `01-current-architecture.md`

包括：

- C4 Context；
- Container；
- Component；
- 依赖方向；
- Agent 入口；
- 外部系统；
- 数据存储；
- 异步边界。

### 20.3 `02-runtime-flow.md`

至少绘制：

- 正常回答；
- 单次 Tool Calling；
- 多次 Tool Calling；
- Tool 失败；
- SSE 断开；
- 用户取消；
- 服务重启；
- 高风险动作审批。

如果当前不支持某流程，应明确标记“未实现”。

### 20.4 `03-capability-inventory.md`

每个 Tool/Capability 包含：

| 字段 | 内容 |
|---|---|
| 名称 | 稳定能力名 |
| 实现 | 文件与符号 |
| 输入 Schema | 当前定义 |
| 输出 Schema | 当前定义 |
| 副作用 | none/read/write/external |
| 权限 | 当前检查 |
| 超时 | 当前配置 |
| 重试 | 当前策略 |
| 幂等 | 当前能力 |
| 风险 | low/medium/high/critical |
| 测试 | 测试文件 |
| 问题 | Gap ID |

### 20.5 `07-gap-analysis.md`

按以下维度评分 0–4：

- Runtime Ownership；
- Structured Contracts；
- Capability Management；
- Policy & Authorization；
- Persistence & Recovery；
- Error Handling；
- Cancellation；
- Streaming；
- Context Management；
- Memory；
- Observability；
- Evaluation；
- Security；
- Provider Independence；
- Testability。

评分：

```text
0 = 不存在
1 = 零散或隐式实现
2 = 基本可用但缺少统一边界
3 = 结构完整，仍有生产缺口
4 = 满足本文主要 MUST 与 SHOULD
```

### 20.6 `11-task-backlog.md`

每个任务必须：

- 单一目标；
- 可由廉价模型理解；
- 限定允许修改的文件范围；
- 列出禁止修改区域；
- 给出前置任务；
- 给出验收测试；
- 给出回滚方式；
- 控制在一次 PR 可审查范围内。

---

## 21. Gap 严重度

### P0：立即阻断

- 跨用户数据访问；
- Secret 进入模型或日志；
- 模型可直接执行任意 SQL/Shell；
- 未授权外部副作用；
- 重试导致重复扣费、发送或删除；
- 可被 Tool Output 注入绕过策略。

### P1：高优先级

- 无 Run 级预算；
- 无取消；
- 无超时；
- 写操作无幂等；
- HTTP/SSE 断开导致未知状态；
- 多个编排中心；
- Tool 绕过 Domain Authorization；
- 无结构化错误；
- 无审计事件。

### P2：中优先级

- Provider 耦合；
- Tool Schema 不一致；
- Context 无限增长；
- 大结果直接塞入 Prompt；
- 无 Artifact；
- 无配置版本；
- 测试覆盖不足。

### P3：改进项

- 命名不统一；
- 目录边界不清；
- Metrics 不完整；
- 文档缺失；
- 可维护性改进。

---

## 22. OtakuNeko 的初始对照入口

根据项目公开说明，OtakuNeko 当前采用：

- FastAPI 后端；
- Next.js 前端；
- LangGraph ReAct Agent；
- SSE 流式响应；
- 多模型兼容接口；
- 多个动漫领域 Tool；
- SQLite / PostgreSQL 双模式；
- Redis；
- JWT 与 BYOK。

这些信息只能作为审计入口。Codex 必须从源码验证：

1. LangGraph 是仅用于局部 Agent Loop，还是已经承担完整 Run Runtime；
2. SSE 是否只是展示层，还是运行生命周期依赖 SSE；
3. 7 个 Tool 是否直接调用 Service，是否执行用户级授权；
4. Tool 是否有统一输入输出 Schema；
5. Tool Result 是否被安全裁剪；
6. 用户身份是否通过不可伪造的 Context 传入 Tool；
7. SQLite 与 PostgreSQL 下 Run 持久化语义是否一致；
8. Redis 是缓存、消息总线、锁还是 Run 状态存储；
9. 多模型兼容是否通过统一 Model Gateway；
10. `generate_user_profile_tool` 是否隐藏了嵌套 LLM/Workflow；
11. qBittorrent 等外部副作用是否需要审批、幂等和审计；
12. JWT、BYOK、模型日志和 Trace 是否可能泄漏凭据。

---

# 第三部分：推荐迁移路线

## 23. 迁移原则

### 23.1 先观测，后替换

先建立 Run ID、Event、Trace 和契约，再改变运行逻辑。

### 23.2 先建立边界，后拆模块

不要先做大规模移动文件。先定义接口并用 Adapter 包裹现有实现。

### 23.3 先只读能力，后写能力

优先规范查询型 Tool，再处理日历、下载、收藏修改等副作用能力。

### 23.4 保持垂直切片可运行

每一批改动结束时：

- 应用可启动；
- 现有 API 尽量兼容；
- 测试通过；
- 至少一个真实用户流程可用；
- 有明确回滚点。

## 24. 推荐批次

### Batch 0：建立基线

- 补齐测试；
- 固定关键依赖版本；
- 记录当前 Agent 行为；
- 建立 Eval Dataset；
- 不修改业务行为。

### Batch 1：统一契约

- `RunRequest`
- `AgentDecision`
- `InvocationRequest`
- `InvocationResult`
- `RunEvent`
- `RunResult`
- 错误分类

使用 Adapter 兼容现有 LangGraph 与 Tool。

### Batch 2：引入 Capability Registry

- 将 Tool 元数据集中；
- 标记副作用和风险；
- 统一输入输出 Schema；
- 建立 Agent Allowlist；
- 不改变 Tool 内部业务实现。

### Batch 3：提取 Model Gateway

- 隔离 LangChain/OpenAI-compatible 细节；
- 统一 Streaming；
- 统一 Usage；
- 统一错误；
- 增加模型版本记录。

### Batch 4：建立 Runtime Coordinator

- 明确 Run 所有者；
- 引入步数和预算；
- 统一 Tool 调度；
- 统一终止条件；
- 保留 LangGraph 作为内部 Workflow，或逐步缩小其职责。

### Batch 5：持久化 Run 与 Event

- Run Store；
- Step/Invocation；
- Event sequence；
- SSE 补拉；
- 断线不丢 Run。

### Batch 6：Checkpoint、暂停与恢复

- Checkpoint；
- 用户输入暂停；
- Approval；
- 重启恢复；
- 取消传播。

### Batch 7：安全与副作用治理

- Principal；
- Tool 级授权；
- 幂等；
- Approval；
- Secret 脱敏；
- Prompt Injection 测试；
- Sandbox。

### Batch 8：Context、Memory 与 Artifact

- Context Compiler；
- Token Budget；
- Summary；
- Memory Policy；
- Artifact Store；
- 大结果引用。

### Batch 9：Observability 与 Eval 门禁

- OpenTelemetry Trace；
- Metrics；
- Eval Runner；
- 回归基线；
- CI Gate。

### Batch 10：Subagent 与动态能力

只有在单 Agent Runtime 稳定后再引入：

- Agent Registry；
- Delegation Contract；
- 子 Agent 预算；
- 权限隔离；
- 结果证据；
- 级联失败控制。

---

## 25. 每批任务的验收模板

```markdown
# TASK-HARNESS-XXX

## 目标
一句话描述本任务唯一目标。

## 背景
对应的 Gap ID 和规范条款。

## 允许修改
- `path/a.py`
- `path/b.py`

## 禁止修改
- API 响应结构
- 数据库业务表
- 前端交互
- 未列出的模块

## 实施要求
1. ...
2. ...
3. ...

## 兼容要求
- ...
- ...

## 测试
- 单元测试：
- 集成测试：
- 回归测试：
- 手工验证：

## 验收标准
- [ ] ...
- [ ] ...
- [ ] ...

## 回滚
说明如何恢复到修改前实现。

## 输出
- 修改文件列表
- 测试结果
- 未解决问题
- 风险说明
```

---

# 第四部分：可直接交给 Codex 的提示词

## 26. 首轮审计提示词

```text
你正在审计并规划重构仓库 ShowayLiao/OtakuNeko 的 AI Agent Harness。

权威对照文档：
docs/architecture/standard-agent-harness-reference.md
如果该文件路径不同，请先找到本文档的实际路径。

本轮目标：
只做源码审计和文档输出，不修改生产代码，不移动文件，不升级依赖。

必须完成：
1. 阅读仓库根目录、backend、frontend、tests、docs 和部署配置。
2. 找到所有与 LLM、LangGraph、Tool、SSE、Memory、Session、数据库、
   Redis、认证、BYOK、外部副作用和日志有关的实现。
3. 画出真实的当前运行流程。以源码为准，不以 README 为准。
4. 将每个现有模块映射到参考 Harness 组件。
5. 识别缺失、职责混乱、重复实现、隐藏副作用、安全边界和恢复问题。
6. 使用本文 §20 定义的目录和文件名输出审计文档。
7. 每个结论必须引用文件路径和符号；能确定时附行号。
8. 每个 Gap 必须包含严重度、证据、风险、建议、前置依赖和置信度。
9. 不得声称“标准要求必须使用某个框架”。
10. 不得在证据不足时猜测。使用“未确认”并说明需要检查什么。

重点检查：
- Agent Loop 的唯一所有者；
- LangGraph 与应用 Runtime 的职责边界；
- Tool Registry、Schema、权限和结果归一化；
- 用户身份是否能被模型伪造；
- SSE 断开后的 Run 状态；
- 服务重启后的恢复；
- Tool 重试和副作用幂等；
- qBittorrent、日历、收藏修改等高风险能力；
- Prompt / Tool Output Injection；
- BYOK 和 Secret 泄漏；
- 多模型 Adapter；
- Token、费用、步数和超时预算；
- Trace、Event、Eval 和测试；
- SQLite/PostgreSQL 模式的一致性。

输出目录：
docs/harness-audit/

最后在终端输出：
- 创建的文档列表；
- 当前成熟度等级；
- P0/P1 Gap 数量；
- 推荐的前三个重构 Batch；
- 仍未确认的关键问题。

禁止：
- 修改业务代码；
- 自动格式化全仓库；
- 删除文件；
- 修改数据库迁移；
- 引入新框架；
- 根据目标架构伪造当前实现。
```

## 27. 审计后的规划提示词

```text
读取：
- 标准 Harness 参考文档；
- docs/harness-audit/ 下全部审计结果；
- 当前源码和测试。

本轮只生成可执行重构任务，不修改生产代码。

要求：
1. 将 Gap 按依赖关系排序。
2. 优先处理 P0/P1，但避免一次性大重写。
3. 每个任务控制在一个可审查 PR。
4. 使用本文 §25 的任务模板。
5. 每个任务必须列出允许修改和禁止修改的文件范围。
6. 每个任务必须包含测试与回滚。
7. 对低成本代码模型给出足够明确的接口、数据结构和边界条件。
8. 先用 Adapter 包装现有实现，再逐步替换。
9. 不允许同时重构 Runtime、数据库、前端协议和全部 Tool。
10. 保持每批结束后应用可运行。

输出：
docs/harness-tasks/
  INDEX.md
  BATCH-00/
  BATCH-01/
  ...

INDEX.md 必须包含：
- 任务依赖图；
- 每批目标；
- 风险；
- 预计影响模块；
- 验收门禁；
- 回滚点。
```

## 28. 单任务执行提示词

```text
只执行指定的 TASK-HARNESS-XXX。

执行前：
1. 阅读任务文件、标准 Harness 文档和相关审计 Gap。
2. 检查任务前置条件是否已满足。
3. 查看允许修改和禁止修改范围。
4. 运行现有相关测试，记录基线。

执行中：
- 不扩大范围；
- 不顺手重构无关代码；
- 不修改公共 API，除非任务明确要求；
- 不隐藏兼容层；
- 不删除旧实现，除非新旧路径已经通过测试；
- 所有新契约必须有 Schema 与单元测试；
- 所有副作用必须考虑权限、超时、取消和幂等；
- 所有异常必须映射到结构化错误；
- 保持类型检查和 lint 通过。

执行后：
1. 运行任务要求的测试。
2. 运行受影响模块的回归测试。
3. 输出修改文件和关键设计决策。
4. 输出测试命令与结果。
5. 输出未解决问题和风险。
6. 对照验收清单逐项说明。
7. 如果前置条件不满足，停止修改并给出证据，不得猜测实现。
```

---

# 第五部分：完成定义

## 29. Harness 基础完成定义

当项目满足以下条件时，可认为达到可靠的 Level 2：

- [ ] Run Coordinator 是唯一 Run 控制者；
- [ ] 模型只能提出结构化 Decision；
- [ ] Tool 通过统一 Registry 注册；
- [ ] Tool 输入输出有 Schema；
- [ ] 每个 Tool 有副作用和风险标记；
- [ ] Policy 在执行前检查权限；
- [ ] Domain Service 进行资源级授权；
- [ ] 有统一 InvocationResult 和错误分类；
- [ ] 有最大步数、超时、重试和取消；
- [ ] 有 Run ID、Trace ID 和 Invocation ID；
- [ ] 多模型通过 Model Gateway；
- [ ] 关键路径有单元和集成测试；
- [ ] 有基本 Agent Eval；
- [ ] 无 Secret 进入模型和普通日志。

## 30. Durable Harness 完成定义

达到 Level 3 还需要：

- [ ] Run、Step、Invocation 和 Event 持久化；
- [ ] Checkpoint；
- [ ] 服务重启恢复；
- [ ] SSE 断线补拉；
- [ ] Human Approval；
- [ ] 写操作幂等；
- [ ] Artifact Store；
- [ ] Context Budget；
- [ ] Memory Policy；
- [ ] 全链路身份传播；
- [ ] OpenTelemetry Trace；
- [ ] Eval 回归门禁；
- [ ] 安全测试覆盖 Prompt Injection 和越权。

---

## 31. 非目标

本文不要求：

- 所有 Agent 都采用多 Agent；
- 所有流程都交给 LLM；
- 使用微服务；
- 使用 Event Sourcing；
- 使用向量数据库；
- 使用 MCP；
- 使用某个特定云平台；
- 一次性替换 LangGraph；
- 为个人项目搭建过度复杂的平台。

Harness 的目标是建立**清晰、可控、可恢复、可观察和可测试的执行边界**，而不是增加抽象数量。

---

## 32. 参考资料

以下资料用于提炼共同能力，不代表本文绑定其具体实现：

1. OpenAI Agents SDK：Agent Loop、Tools、Handoffs、Guardrails、Human-in-the-loop、Tracing  
   https://openai.github.io/openai-agents-python/

2. Google Agent Development Kit：Runtime Event Loop、Events、Sessions、State、Artifacts  
   https://google.github.io/adk-docs/

3. LangGraph：Persistence、Checkpoint、Interrupt、Durable Execution  
   https://docs.langchain.com/oss/python/langgraph/overview

4. Model Context Protocol Specification：Tools、Resources、Prompts 与客户端/服务端边界  
   https://modelcontextprotocol.io/specification/

5. OpenTelemetry Semantic Conventions：GenAI 与 Agent 可观测性  
   https://opentelemetry.io/docs/specs/semconv/

6. NIST AI Risk Management Framework 与 Generative AI Profile  
   https://www.nist.gov/itl/ai-risk-management-framework

7. OWASP AI Agent Security Cheat Sheet 与 Agentic Applications 风险资料  
   https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html  
   https://genai.owasp.org/

---

## 33. 最终架构判断原则

在任何具体技术选择发生冲突时，优先使用以下判断：

```text
是否让 Runtime 更清楚地拥有执行控制？
是否让模型权限更小而不是更大？
是否让副作用更显式？
是否让状态可以持久化和恢复？
是否让接口更结构化和可版本化？
是否让错误、成本和行为更可观察？
是否让测试能够在不调用真实模型的情况下覆盖运行逻辑？
是否让业务服务摆脱具体 Agent 框架依赖？
```

如果答案大多为“是”，该修改通常符合现代 Harness 的演进方向。
