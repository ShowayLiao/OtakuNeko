# Agents 模块

Agent 的运行循环由 `app.harness.runtime.AgentRuntime` 控制。模型只能返回
版本化的 `AgentDecision`，能力调用必须经过 `Dispatcher`、`CapabilityRegistry`
和 `ExecutionContext` 的授权边界。

## 目录职责

- `app/api/v1/agent.py`：聊天 SSE 与 Run/Thread 投影；不持有模型循环。
- `app/harness/runtime.py`：执行 Decision、预算、取消、checkpoint 与 canonical Run 事件。
- `app/capabilities/`：Capability、Action schema、授权和结果契约。
- `app/agents/tools/`：尚未迁移的领域函数与日志边界；它们不是模型可直接执行的工具目录。
- `app/agents/agent_registry.py`、`router.py` 等：仅供仍有明确调用方的专用业务路径使用。

## 事件与持久化

`AgentRuntime.stream_decision()` 产出 `message_input`、`thinking_*`、
`model_*`、`tool_call_*`、`message_*` 和 `run_*` 事件。认证用户的 Run/Event
事实写入 `RunStore` 与 `EventStore`，SSE 只负责投影，不是 Run 状态的唯一来源。

历史、线程和推理接口从 canonical Run/Event Store 读取；旧的 LangGraph Graph、
事件适配器和 singular `tools.py` 兼容层已移除。LangGraph 依赖仍可能被 Memory
迁移边界使用，不能据此推断它是聊天主循环。
