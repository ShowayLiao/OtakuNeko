# Observability、Event、Eval 与测试覆盖

## Trace / Event 当前实现

`AgentTrace` 定义 trace id、task/user、agent、goal、status、steps、duration/error；事件类型覆盖 node、routing、capability、MCP、model、retry、failure、tool call 和 agent result（`backend/app/trace/__init__.py:1-180`）。`TraceRecorder` 使用 ContextVar 保存当前 recorder，span 会记录安全参数形状和脱敏数据（`backend/app/trace/recorder.py:1-220`）。

SQL store 可写 `agent_trace` 与 `trace_event`，并按 user id 查询；但聊天 API 把 `SqlTraceStore(db)` 传给 Runtime，而 Runtime 的 record 主要在 stream 成功/异常结束时发生，未形成每个 SSE sequence 的实时 durable event（`backend/app/api/v1/agent.py:176-219`; `backend/app/harness/runtime.py:181-336`; `backend/app/trace/sql_store.py:1-220`）。

Graph/adapter 有 Tool/Node/Route span，说明边界 instrumentation 已开始建立（`backend/app/agents/langgraph_adapter.py`; `backend/app/trace/recorder.py`）。然而没有统一的 `Run ID + Step ID + Invocation ID + stream sequence` 贯穿 API、Runtime、Graph、Tool、SSE 和 SQL；`trace_id` 和 `thread_id` 仍是并行标识。

日志目前记录了工具参数截断、异常字符串、qBittorrent URL/rule payload；未统一调用 `trace.redaction`（`backend/app/agents/tools/base.py:20-58`; `backend/app/services/qb_service.py:103-112,180-198`; `backend/app/core/logging.py:33-147`）。

## SSE 消费协议

后端每个 chunk 附 `stream_sequence`、elapsed 和可选 public thread id，再以 `event: chunk.type` 输出；前端解析 `event:`/`data:`，忽略 JSON 解析错误，按类型回调（`backend/app/api/v1/agent.py:220-231`; `frontend/src/lib/fetcher.ts:46-73,172-272`）。

已有内容：thinking/message/tool/progress/error 事件、客户端 timeout、AbortSignal、前端事件顺序合并测试（`frontend/src/hooks/useChatStreaming.ts:325-584`; `frontend/src/lib/fetcher.test.ts`）。缺少：`id`、`run_id`、`invocation_id`、事件持久化、`Last-Event-ID`、重连补拉、服务端状态查询和“断开后到底成功/失败/取消”的权威状态（G-P1-03、G-P1-06）。

## Eval 实现

仓库有 `backend/app/evaluation/{dataset,runner,metrics,judge,reporting}.py`，并有 CLI entry `otakuneko-eval`（`backend/pyproject.toml:42-43`; `backend/app/evaluation/runner.py:1-260`）。测试覆盖 dataset、runner、metrics、judge、CLI（`backend/tests/evaluation/test_dataset.py`; `test_runner.py`; `test_metrics.py`; `test_judge.py`; `test_cli.py`）。Judge 测试有 cost budget，metrics 测试有 latency/call budget（`backend/tests/evaluation/test_judge.py:110-128`; `backend/tests/evaluation/test_metrics.py:76-84`）。

但这些预算和评估 runner 没有接入交互聊天主路径的 `AgentRuntime`/Graph Loop；主路径只在 graph 层有 24 步 recursion limit，未记录 token、费用、模型响应 usage 或 Tool 选择质量（`backend/app/agents/graph.py:20,242-247`; `backend/app/harness/runtime.py:181-305`; `backend/app/harness/model_gateway.py:32-73`）。参考文档要求评估 Task Success、Tool Selection/Argument、Policy、Side-effect、Recovery、Cost、Latency 等（参考文档:1328-1343），当前实现尚未形成这些维度的聊天回归门禁。

## 测试覆盖矩阵

| 领域 | 已有测试证据 | 审计判断 |
|---|---|---|
| Harness task/state/runtime | `tests/harness/test_task.py`, `test_state.py`, `test_runtime.py`, `test_serialization.py` | 单元契约较完整；主聊天 wiring 未作为真实 FastAPI + DB + SSE 集成测试。 |
| LangGraph/checkpoint | `tests/agents/test_graph_checkpoint.py`, `test_workflow_lifecycle.py`, `test_langgraph_adapter.py` | 覆盖临时 SQLite、生命周期、adapter；没有 Docker 重启/云模式 checkpoint 测试。 |
| Tool/Capability | `tests/agents/tools/test_base.py`, `tests/capabilities/*` | 有 schema/parity/registry；没有统一主聊天 Registry、result redaction、权限上下文的端到端测试。 |
| MCP | `tests/mcp/*`, `tests/agents/mcp/*` | policy/idempotency/transport 有专门覆盖；MCP 未接入主聊天，所以不能证明聊天主路径安全。 |
| Memory | `tests/memory/*` | SQL repository、retention、migration、logging 有覆盖；Memory poisoning/外部 Tool output 注入未见测试。 |
| Trace | `tests/trace/*` | redaction、SQL scope、boundary span、runtime instrumentation 有覆盖；断线中途 event durability 未覆盖。 |
| Proactive | `tests/proactive/test_scheduler.py` | lease/claim 方向有覆盖；scheduler 和 interactive chat 状态分裂。 |
| qBittorrent/RSS | 当前清单未发现对应 `backend/tests` API auth/replay/compensation 集成测试 | G-P0-01/G-P1-04 的测试空白。 |
| 前端 SSE | `frontend/src/lib/fetcher.test.ts` | 认证转发有测试；未见 Last-Event-ID/断线恢复/服务端 Run 查询测试。 |
| 安全 | trace redaction/provider endpoint 有测试 | 未见 Prompt Injection、Tool Output Injection、SSRF DNS、越权 qBittorrent 集成测试。 |

## 评估结论

当前仓库不是“没有测试”，而是测试集中在已拆分的 Harness/MCP/Capability 单元和计划中的契约上，尚未覆盖**真实聊天主路径的组合行为**。最优先新增的是：qBittorrent auth negative test、主路径 fake provider + fake Tool 的 Run state test、SSE disconnect/reconnect、Graph error status、user identity injection、cost/step/time budget。
