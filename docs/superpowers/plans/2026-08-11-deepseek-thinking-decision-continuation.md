# DeepSeek 思考模式多轮 Decision 修复计划

日期：2026-08-11

## 背景与根因

Runtime-owned Decision Loop 在一次 Capability 调用后，会把结果作为普通 `role=user` 消息追加给下一轮模型，但没有把上一轮模型的 assistant 消息及 DeepSeek 的 `reasoning_content` 一并放回请求历史。当前 `OpenAIModelGateway.infer()` 还会在 provider 边界统一裁剪消息字段，因此即使 Runtime 补充字段，也必须由 DeepSeek adapter 有条件地投影。思考模式下第二轮请求因此可能被 DeepSeek 判定为无效 continuation，表现为 `invalid_request`。

## 目标

- DeepSeek 思考模式可以完成“模型提出 invoke → Runtime 调度 Capability → 模型继续 Decision → respond/finish”的多轮路径。
- 继续保持 LLM 只能提出结构化 Decision，Capability 仍只由 Dispatcher 执行。
- provider-specific 字段只停留在 Model Gateway adapter 边界；OpenAI-compatible 其他 provider 不收到 `reasoning_content`。
- 不新增原始推理的 Trace、Memory 或 durable Checkpoint 存储；现有 `thinking_chunk` SSE 展示契约不在本次修复范围内。
- 保持现有取消、超时、解析失败、审批恢复和旧兼容路径的行为。

## 实施步骤

### 1. 基线与失败测试

- 运行现有 `test_reasoning_forwarding.py`、`test_runtime_orchestration.py` 和主路径 acceptance 测试。
- 在后端 Harness 测试中增加一个 fake DeepSeek continuation 场景：第一轮返回带 `text` 与 `reasoning` 的 invoke Decision，第二轮断言消息顺序为 `user → assistant(reasoning) → user(tool feedback)`。
- 增加 adapter 边界测试：DeepSeek 将 assistant 的 `reasoning` 映射为 `reasoning_content`，普通 OpenAI-compatible provider 过滤该字段。
- 先运行新增测试并确认当前实现失败。

### 2. Runtime continuation

- 在 `backend/app/harness/runtime.py` 增加 provider-neutral 的 assistant continuation 构造逻辑，使用模型的结构化文本；fake gateway 仅有 `decision` 时使用数据化 JSON 作为兼容内容。
- 在 Decision 解析成功后、保存 pending decision 前，将 assistant continuation 放入本轮内存消息；解析失败的可恢复重试也先保存上一轮 assistant，再追加 repair prompt。
- Capability 成功后继续追加现有不可信 `role=user` feedback，保持当前非原生 tool-call 协议。
- 写入 Checkpoint 的 `decision_messages` 时移除 `reasoning`，避免原始推理进入持久化状态；仅当前 Runtime 调用链在内存中携带该字段。

### 3. Model Gateway adapter 投影

- 在 `backend/app/harness/model_gateway.py` 的消息安全投影中，DeepSeek 将 assistant 消息上的统一 `reasoning` 映射为 API 所需的 `reasoning_content`。
- 对其他 provider 继续只发送现有 `role/content` 字段。
- 不改变 JSON Decision response format、thinking options、usage/error 归一化或外部能力调用权限边界。

### 4. 验证与审查

- 先通过 focused regression tests，再运行后端全量 pytest 和 Ruff。
- 执行 `git diff --check`、`git diff --stat`，审查完整未提交 diff，确认没有前端、依赖、Secret、raw provider payload 或生成文件变化。
- 若完整验证受环境限制，记录具体命令、退出码和未运行原因；不创建 Batch execution record，不提交代码。

## 允许修改范围

- `backend/app/harness/runtime.py`
- `backend/app/harness/model_gateway.py`
- `backend/tests/harness/`
- 必要时对应的 `backend/tests/acceptance/`
- 本计划文件

## 回滚

回滚本次未提交的上述文件修改即可；不改变 `HARNESS_PRIMARY_DECISION_LOOP_ENABLED`，不删除现有 Decision/Dispatcher 契约，也不影响旧兼容路径。
