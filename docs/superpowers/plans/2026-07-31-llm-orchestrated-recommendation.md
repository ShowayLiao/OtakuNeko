# 通用 LLM 主脑式 Harness 编排改进计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前会话中按任务执行，并在每个检查点运行验证。

**目标：** 建立通用的 LLM 主脑式 Harness：LLM 负责理解任务、决定是否调用工具/Capability/Subagent 和最终整合；执行单元只负责完成可验证的子任务并返回结构化事实。推荐只是首个接入场景，同时支持单纯问答、单个 Capability 和未来的多步 Subagent 协作。

**架构：** `/chat` 为每次请求创建带模型上下文的 AgentRuntime；Runtime 通过统一注册表和执行协议调度 Capability 或 Subagent，接收结构化 `agent_result` 后将其作为工具结果回传给 LLM，再流式输出 LLM 生成的最终回答。没有工具需求时走直接问答；LLM 编排失败时使用确定性降级回答。旧 LangGraph 回退路径继续保留。

**技术栈：** FastAPI、AsyncOpenAI、现有 AgentRuntime、FeatureFlagRoutingAdapter、LangGraph trace、pytest。

---

## 当前断点与目标链路

当前链路在 `FeatureFlagRoutingAdapter` 中提前结束：

```text
路由 → 任意 Capability/Subagent.execute → 固定模板或直接 message_chunk
```

目标链路：

```text
用户请求
  → LLM 主脑理解任务并决定：直接回答 / 调用 Capability / 调用 Subagent
  → 执行单元返回结构化 agent_result
  → AgentRuntime 将结果作为工具结果回传给 LLM
  → LLM 结合原始请求和工具结果生成最终回答
  → 用户
```

任何执行单元都不得把未经 LLM 整合的中间结果当作最终回复；LLM 调用失败时才允许使用该执行单元提供的确定性降级渲染器。

## 通用 Harness 设计约束

### 执行模式

1. **Direct QA：** 没有可调用工具时，LLM 直接回答，不强行创建 Subagent。
2. **Capability：** LLM 选择一个注册的 Capability，Capability 返回结构化数据，Runtime 将结果回传给 LLM。
3. **Subagent：** LLM 选择一个注册的 Subagent；Subagent 可以在内部调用多个 Capability，但对 Runtime 只暴露统一的 `AgentResult`。
4. **Multi-step：** LLM 可基于上一步结果继续调用其他 Capability/Subagent，直到满足完成条件或达到预算。

### 扩展边界

- `AgentRuntime` 只依赖通用协议，不认识推荐、动画、收藏等领域字段。
- `AgentRegistry` 同时注册 Capability Adapter 和 Subagent Adapter，名称、输入 schema、输出 schema、权限和预算声明都属于注册元数据。
- `ModelGateway` 是唯一的模型调用入口，统一处理 provider、模型、超时、预算、重试和 `model_call` trace。
- `AgentResult` 是执行单元和 LLM 之间的稳定边界；LLM 只消费经过脱敏和大小限制的 `data/evidence`。
- 确定性路由可以作为清晰意图的低延迟优化，但不能跳过“结果回传给 LLM”的整合阶段。

## 任务 1：定义通用 AgentResult 与 ModelContext 契约

**文件：**

- 创建：`backend/app/harness/result.py`
- 创建：`backend/app/harness/model_gateway.py`
- 测试：`backend/tests/harness/test_result_contract.py`
- 测试：`backend/tests/harness/test_model_gateway.py`

- [ ] **步骤 1：编写失败测试**

测试以下契约：

```python
result = AgentResult(
    kind="subagent",
    name="recommendation",
    status="completed",
    data={"candidates": [{"id": 1}]},
    evidence={"source": "profile"},
)
assert result.kind == "subagent"
assert result.name == "recommendation"
assert result.data["candidates"]
```

模型网关测试使用假的 AsyncOpenAI client，验证 `generate()` 能接收模型、温度、消息和工具结果，并返回文本；不得访问真实网络。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
pytest backend/tests/harness/test_result_contract.py backend/tests/harness/test_model_gateway.py -q
```

预期：因 `AgentResult` 和 `ModelGateway` 尚未存在而失败。

- [ ] **步骤 3：实现最小契约**

`AgentResult` 使用项目现有类型风格定义以下字段：

- `kind`：`capability` 或 `subagent`
- `name`：注册表中的执行单元名称
- `status`：`completed`、`degraded`、`failed`
- `data`：供 LLM 使用的结构化业务结果
- `evidence`：可审计但不包含私密原文的证据
- `error_code`：可选的机器可读失败原因

`ModelContext` 保存当前请求的 `api_key`、`base_url`、`model`、`temperature` 和深度思考选项。`ModelGateway` 负责一次模型生成、超时、异常分类和 `TraceEventType.MODEL_CALL` 记录，不把 Provider 细节泄漏给 Subagent。

- [ ] **步骤 4：运行测试确认通过**

运行同上命令，预期全部通过。

## 任务 2：让 RecommendationAgent 作为首个结构化 Subagent 接入

**文件：**

- 修改：`backend/app/agents/recommendation_agent.py`
- 修改：`backend/tests/agents/test_recommendation_agent.py`

- [ ] **步骤 1：编写失败测试**

修改测试，验证推荐成功时：

- `result.kind/name` 正确标识执行单元
- `result.data.candidates` 保留候选列表
- `result.evidence.candidate_search` 保留召回统计
- 不依赖 `response_generator`
- 不把 `_build_response()` 的固定自然语言作为最终结果

同时保留召回失败、无结果和强反感过滤后的原因码测试。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
pytest backend/tests/agents/test_recommendation_agent.py -q
```

预期：现有返回字典结构和固定 `content` 断言暴露新契约未完成。

- [ ] **步骤 3：实现最小改造**

将 `execute()` 的成功返回改为 `AgentResult` 或其兼容字典：

```python
return {
    "kind": "subagent",
    "name": "recommendation",
    "status": "completed",
    "data": {
        "goal": goal,
        "profile": _public_profile_summary(profile),
        "candidates": candidates[: self.max_candidates],
    },
    "evidence": {
        **result.get("evidence", {"source": "profile"}),
        "candidate_search": search_stats,
        "model_calls_used": 0,
    },
}
```

候选数据只保留 LLM 需要的名称、简介、标签、评分、匹配字段和过滤原因；不把完整收藏原文或凭据传给模型。`_build_response()` 改为确定性降级渲染器，仅在编排层模型失败时调用。

- [ ] **步骤 4：运行目标测试确认通过**

运行：

```powershell
pytest backend/tests/agents/test_recommendation_agent.py -q
```

预期：推荐画像、候选召回、强反感过滤和空结果语义测试通过。

## 任务 3：在 AgentRuntime 中实现通用 LLM 整合阶段

**文件：**

- 修改：`backend/app/harness/runtime.py`
- 修改：`backend/app/harness/routing_adapter.py`
- 测试：`backend/tests/harness/test_runtime_orchestration.py`
- 测试：`backend/tests/agents/test_multi_agent_integration.py`

- [ ] **步骤 1：编写失败测试**

使用 fake specialist 和 fake model gateway 验证：

1. Specialist 被调用一次。
2. Specialist 结果被传给 ModelGateway。
3. 最终输出来自 ModelGateway，而不是 specialist 的固定 `content`。
4. 最终输出前后仍能产生 `agent_result`、`model_call` 和 `message_end` 事件。
5. 模型预算为 0 或模型失败时返回降级内容，并保留 Subagent 候选。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
pytest backend/tests/harness/test_runtime_orchestration.py backend/tests/agents/test_multi_agent_integration.py -q
```

预期：当前 Runtime 没有消费 `agent_result` 并调用模型，测试失败。

- [ ] **步骤 3：实现通用编排流程**

为 `AgentRuntime` 增加可选 `model_gateway` 和模型上下文。Adapter 在 specialist 完成后只发出结构化 `agent_result`；Runtime 将以下内容交给网关：

- 用户原始消息
- 当前路由和调用的 Subagent 名称
- Subagent 的 `data`
- Subagent 的 `evidence`
- 当前模型预算和输出约束

Runtime 负责统一记录模型调用、更新状态和流式转发结果。`routing_adapter.py` 不再直接执行：

```python
yield {"type": "message_chunk", "content": result.get("content", "")}
```

而是交给 Runtime 的整合阶段。编排层必须支持无候选结果，让 LLM 能解释原因并给出下一步建议；只有能力异常、策略拒绝或模型调用失败时才进入确定性降级。

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
pytest backend/tests/harness/test_runtime_orchestration.py backend/tests/agents/test_multi_agent_integration.py -q
```

预期：Subagent 结果回传、模型整合、预算和降级测试全部通过。

## 任务 4：支持 Direct QA、Capability 和 Subagent 三种模式

**文件：**

- 创建：`backend/app/harness/orchestrator_prompt.py`
- 修改：`backend/app/api/v1/agent.py`
- 修改：`backend/app/harness/runtime.py`
- 修改：`backend/app/agents/router.py`
- 测试：`backend/tests/harness/test_execution_modes.py`
- 测试：`backend/tests/harness/test_orchestrator_prompt.py`
- 测试：`frontend/src/app/api/v1/chat/route.test.ts`

- [ ] **步骤 1：编写失败测试**

使用同一个 fake ModelGateway 验证三种输入：

- 普通问答不注册工具，模型只被调用一次并直接回答。
- Capability 调用返回结构化工具结果，模型收到工具结果后再生成最终回答。
- Subagent 调用返回结构化 `AgentResult`，模型收到 Subagent 结果后再生成最终回答。

另外验证多步调用可携带前一步结果，且 `request.model`、`temperature` 和 Provider endpoint 能到达 ModelGateway。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
pytest backend/tests/harness/test_execution_modes.py backend/tests/harness/test_orchestrator_prompt.py -q
```

预期：当前 Runtime 只有推荐专用直连路径，没有通用的直接问答、Capability 和 Subagent 编排协议，测试失败。

- [ ] **步骤 3：实现通用编排和提示词**

在 `/chat` 创建 Runtime 时只注入 ModelGateway、注册表和本次请求的 ModelContext；不得在 API 层创建 RecommendationResponseGenerator 等领域专用生成器。

统一提示词要求：

- 先判断是否需要工具；不需要时直接回答。
- 需要工具时选择注册表中的 Capability 或 Subagent，并说明调用目标。
- 只能依据工具结果生成结论，不虚构工具未返回的事实。
- 工具失败或数据不足时诚实说明并给出下一步建议。
- 最终输出适合聊天界面的 Markdown；领域格式（如推荐理由）由领域 Subagent 的结果 schema 和领域提示片段提供。

确定性路由可以作为清晰意图的低延迟优化，但调用结束后仍必须回到 LLM 整合阶段。

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
pytest backend/tests/harness/test_execution_modes.py backend/tests/harness/test_orchestrator_prompt.py -q
```

预期：三种执行模式、多步上下文、参数透传和事实约束测试通过。

## 任务 5：补齐通用 Trace、前端事件和回退行为

**文件：**

- 修改：`backend/app/harness/runtime.py`
- 修改：`backend/app/trace/__init__.py`（仅在缺少事件类型时）
- 修改：`frontend/src/stores/useChatStore.ts`
- 测试：`backend/tests/trace/test_boundary_spans.py`
- 测试：`frontend/src/lib/fetcher.test.ts`

- [ ] **步骤 1：编写失败测试**

对 Direct QA、Capability 和 Subagent 请求分别验证 trace 能表达调用边界；Subagent 推荐场景至少包含：

```text
routing
agent_result
model.synthesis
agent.stream
```

并验证：

- `model_call` 包含模型名、耗时和调用用途
- `agent_result` 记录执行单元名称、状态和脱敏摘要
- 不记录候选简介全文、用户收藏原文或 API Key
- LLM 失败时 trace 标记 `degraded`，而不是伪装成成功

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
pytest backend/tests/trace/test_boundary_spans.py -q
```

预期：当前最新推荐 trace 没有 `model_call`，测试失败。

- [ ] **步骤 3：实现事件和降级输出**

新增或复用 `model.synthesis` 操作名；前端继续将 Capability/Subagent 步骤展示为处理中，将最终 LLM 输出展示为普通 assistant message。降级回答由执行单元提供或由通用 Harness 生成，必须带上内部可观测状态，但不向用户暴露堆栈。

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
pytest backend/tests/trace/test_boundary_spans.py -q
```

预期：事件顺序、脱敏和降级 trace 测试通过。

## 任务 6：增加特性开关并逐步启用

**文件：**

- 修改：`backend/app/core/config.py`
- 修改：`backend/app/api/v1/agent.py`
- 测试：`backend/tests/api/test_agent_endpoint.py`

- [ ] **步骤 1：编写失败测试**

验证：

- `ENABLE_LLM_ORCHESTRATION=false` 时保持旧行为，便于回滚。
- 开关开启且存在模型凭据时走 Subagent → LLM 整合。
- 本地无可用模型时仍能返回通用的确定性降级回答；推荐场景继续保留候选列表降级。

- [ ] **步骤 2：实现开关**

默认在本地环境开启，生产环境先显式配置；开关只控制编排阶段，不影响画像、候选召回和强反感过滤逻辑。

- [ ] **步骤 3：运行 API 测试确认通过**

运行：

```powershell
pytest backend/tests/api/test_agent_endpoint.py -q
```

## 任务 7：通用 Harness 回归验证与手工验收

- [ ] 运行通用 Harness、推荐适配器和 API 相关测试：

```powershell
pytest backend/tests/agents/test_recommendation_agent.py backend/tests/agents/test_multi_agent_integration.py backend/tests/harness backend/tests/trace backend/tests/api -q
```

- [ ] 运行完整后端测试：

```powershell
$env:DEBUG = 'true'
pytest backend/tests -q
```

- [ ] 运行静态检查：

```powershell
ruff check backend/app backend/tests
git diff --check
```

- [ ] 手工发送普通知识问题，确认不调用 Capability/Subagent，LLM 直接回答。

- [ ] 手工发送需要单个 Capability 的请求，确认出现 capability result 后由 LLM 生成最终回答。

- [ ] 手工发送“推荐几部动画给我”，确认 Subagent 结果回到 LLM，回答包含：偏好总结、至少 3 部作品、每部具体理由、评分/标签依据和探索建议。

- [ ] 查询最新 trace，确认至少存在一次 `model_call`，且用途为 `model.synthesis`；确认候选召回仍为成功状态。

- [ ] 关闭模型或模拟模型超时，确认仍返回候选和可理解的降级说明。

## 验收标准

1. 普通问答、Capability、Subagent 三种模式均可由同一套 Harness 执行。
2. 任意执行单元的结构化结果都能回传给 LLM，不能绕过整合阶段直接充当最终答案。
3. 推荐请求不再只返回固定五行模板。
4. `RecommendationAgent` 不负责最终自然语言整合，只返回结构化事实。
5. AgentRuntime 不包含推荐、动画或收藏等领域特例。
6. UI 选择的模型真正出现在最终整合的 `model_call` trace 中。
7. LLM 失败、无候选、候选被反感标签过滤时均有可理解的降级结果。
8. 新增一个 Capability 或 Subagent 只需实现协议并注册，不需要修改 Runtime 核心流程。
9. 现有用户画像、评分中心化、渐进式召回和强反感过滤逻辑保持不变。
10. 完整后端测试、Ruff 和 diff 检查通过。

## 提交边界

实现提交只包含通用 Runtime 编排、ModelGateway、AgentResult 契约、注册适配器、通用提示词、推荐首个接入、测试和必要的前端事件适配；保留工作区中已有的认证、AsyncSession、用户画像和候选召回改动，不执行 reset、checkout 或无关重构。
