# TASK-HARNESS-012

## 目标

收敛 Memory 主路径并建立 Context/Memory trust、provenance、confidence、expiry 和 Prompt/Tool output injection 防护，避免未验证内容晋升为长期事实。

## 背景

对应 `G-P1-07`、`G-P1-10`。主聊天使用 `MemoryServiceImpl`/SQL repository，但 `MemoryManager`/`StoreMemoryRepository` 仍保留另一套 LangGraph Store 语义；事实提取直接把 checkpoint 最近消息交给 LLM，未区分用户指令、Tool output 和已验证事实（`backend/app/api/v1/agent.py:137-150,233-237`; `backend/app/memory/service.py:169-276`; `backend/app/memory/manager.py`; `backend/app/memory/extractor.py`）。用户 `prompt_config` 也会进入 speak system prompt（`backend/app/api/v1/agent.py:106-117`; `backend/app/agents/graph.py:180-193`）。

## 允许修改

- `backend/app/memory/interfaces.py`
- `backend/app/memory/types.py`
- `backend/app/memory/service.py`
- `backend/app/memory/extractor.py`
- `backend/app/memory/sql_repository.py`
- `backend/app/agents/graph.py` 的 context assembly adapter 部分
- `backend/app/agents/tools/base.py` 的 safe result/log adapter 部分
- `backend/tests/memory/test_service_typed.py`
- `backend/tests/memory/test_sql_repository.py`
- `backend/tests/memory/test_memory_logging.py`
- `backend/tests/memory/test_injection.py`
- `backend/tests/agents/test_graph_dual_node.py`

## 禁止修改

- Memory 数据库迁移、历史事实清洗和删除
- qBittorrent、Schedule、Collection 写操作
- 前端协议、Model provider adapter、全部 Tool catalog
- 直接删除 `MemoryManager`/`StoreMemoryRepository`；必须先保留兼容读取/明确 deprecation
- 把任何外部文本用字符串替换假装成安全 policy

## 实施要求

1. 定义 `MemoryFact`/`MemoryContext` provenance 字段：`source_type=user|assistant|tool|external|system`、`source_id`、`confidence`、`verified`、`expires_at`；旧 SQL row 缺省映射为 `source_type=legacy, verified=False`。
2. `ContextCompiler` 将系统 policy、用户偏好、Memory fact、Tool output 分为不同 envelope；Tool/external 内容只能作为 data，不得拼入 system instruction；每个 block 限制最大字符/token。
3. `LLMFactExtractor` 只提取用户明确陈述的稳定事实；输入中标记 untrusted Tool/external 文本，输出 schema 禁止 instruction/credential/approval 字段；未 verified 的 semantic/profile fact 不自动提升为高信任上下文。
4. 统一主路径调用 `MemoryService` port；旧 `MemoryManager` 通过 adapter 调用同一 scope/retention 语义，并在日志中记录 deprecated path，不复制一套写逻辑。
5. Tool result/log adapter 使用 BATCH-03 safe output 和现有 trace redaction；默认不把 raw output 发送给 frontend 或模型 gateway。
6. 为 `prompt_config` 设置长度、字段和 trust 边界；它只能表示用户偏好/语气，不得覆盖固定安全 policy、工具权限、身份或 approval。

## 兼容要求

- 用户 Memory API 的查询、清除、retention 上限保持兼容。
- 没有 embedding/metadata 的 legacy facts 可以读取，但显示 `verified=False`，不伪造 provenance。
- 现有 Chat/SSE event name 不变；只改变传给模型的内部 context envelope。
- `MemoryService.retrieve_context` 在无 checkpoint/无 facts 时仍返回空安全上下文，不抛出 raw error。

## 测试

- 单元测试：provenance 映射、未验证事实过滤、expiry/retention、scope/删除、context block 大小。
- 安全测试：Tool output 中包含“忽略系统策略/泄露 key/批准写操作”时，不能改变 policy/identity/approval，也不能进入高信任 Memory。
- 集成测试：fake extractor 只接受用户明确事实；SQL repository rollback/commit；legacy Store adapter 与 SQL 主路径 scope parity。
- 回归测试：`cd backend && uv run pytest tests/memory tests/agents/test_graph_dual_node.py tests/trace/test_event_contract.py -q`。
- 手工验证：使用恶意外部动漫简介和自定义 persona 完成只读回答，检查模型得到的是 data block，Trace/日志无 raw secret。

## 验收标准

- [ ] Memory facts 有 provenance/confidence/verification/expiry 语义。
- [ ] Tool/external output 不再作为 system instruction 或高信任长期事实。
- [ ] SQL 与 legacy Memory adapter 的 user/thread scope 一致，未删除旧实现。
- [ ] prompt_config 不能覆盖身份、policy、Tool allowlist 或 approval。
- [ ] Memory/API/Graph/Trace 回归测试通过，无数据库迁移。

## 回滚

通过 `MEMORY_TRUST_MODE=legacy-read-safe` 回退为只读兼容读取，禁止恢复未经标记的写入；保留 provenance 字段在内存 adapter 中，失败时不清除用户 facts。禁用新 context compiler 时仍使用 system policy 与 safe output，不能回退到 raw Tool output。

## 输出

- 修改文件列表：记录 Memory port/types/service/extractor、context/tool adapter 和测试。
- 测试结果：报告 scope、injection、provenance、retention、legacy parity。
- 未解决问题：记录历史 facts 的批量标注/迁移需要独立数据任务。
- 风险说明：说明 LLM fact extraction 仍是额外模型调用，预算由 BATCH-05/13 观测。
