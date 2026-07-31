# TASK-HARNESS-013

## 目标

把 Run/Invocation/Model/Tool/Memory 的安全事件接入 Trace/Metrics/Eval，建立聊天主路径的回归门禁和成本/延迟/恢复指标。

## 背景

对应 `G-P1-03`、`G-P1-05`、`G-P1-06`、`G-P1-09`、`G-P1-10`。仓库已有 `AgentTrace`、SQL Trace、redaction、Eval runner/judge/metrics 和大量单元测试，但交互聊天没有完整 Run/Event 投影、token/cost、断线恢复、Tool selection、Policy/Injection 的回归门禁（`backend/app/trace/sql_store.py`; `backend/app/trace/redaction.py`; `backend/app/evaluation/runner.py`; `backend/tests/evaluation/*`; `docs/harness-audit/06-observability-and-evals.md`）。参考文档 Batch 9 要求 Trace、Metrics、Eval baseline 和 CI gate（参考文档:1999-2005）。

## 允许修改

- `backend/app/trace/__init__.py`
- `backend/app/trace/recorder.py`
- `backend/app/trace/sql_store.py`
- `backend/app/evaluation/types.py`
- `backend/app/evaluation/metrics.py`
- `backend/app/evaluation/runner.py`
- `backend/app/evaluation/reporting.py`
- `backend/tests/trace/` 中对应事件/SQL 测试
- `backend/tests/evaluation/` 中对应指标/门禁测试
- `.github/workflows/` 中新增只读测试 job（如仓库 CI 已存在）

## 禁止修改

- 生产业务行为、模型选择、Tool schema、数据库 migration
- 通过关闭 redaction 或记录 raw Prompt 来提高观测性
- 将 Eval judge 的预算替代 Runtime production budget
- 修改前端展示逻辑、qB/Collection/Schedule Service

## 实施要求

1. Trace event 与 BATCH-02/06 使用同一 `run_id、event_id、sequence、invocation_id、provider、model、usage、latency、error_code`；Trace 是查询/诊断投影，不创建第二套状态机。
2. `TraceRecorder` 默认记录字段形状、长度、计数和 hash，不记录完整 prompt/tool output；复用 `sanitize_trace`，redaction 失败时丢弃敏感 payload 但保留事件类型/错误码。
3. Metrics 至少提供 `run_success_rate、tool_success_rate、policy_denied_count、budget_exceeded_count、cancelled_count、reconnect_count、model_tokens、estimated_cost_unknown_count、latency_ms`；unknown usage 不作为零成本。
4. Eval dataset 覆盖 normal、tool selection/args、tool failure、policy deny、identity spoofing、prompt/tool output injection、Memory poisoning、timeout/cancel/reconnect、multi-provider 和 qB unauthorized；真实 secret 全部使用假值。
5. CI gate 只在已有测试命令上增加门槛：契约/安全/恢复测试失败则阻断；LLM judge 结果记录模型版本、dataset version、budget，不把非确定性文案相似度作为唯一门槛。
6. 报告每个 PR 修改 Prompt、Tool schema、Model adapter、Memory、Policy 或 Loop 时运行相关 Eval；保留 baseline 和差异原因。

## 兼容要求

- 现有 Trace query/list API 的 user scope 和 redaction 保持兼容。
- 现有 Eval CLI `otakuneko-eval`、dataset/runner/judge API 保持兼容，新增指标可选输出。
- CI 无外部 provider 时使用 fake adapter；真实 provider 评估不得成为单元测试必需依赖。
- Trace/event schema 版本化，旧 trace 可读取并映射为 `legacy` version。

## 测试

- 单元测试：event correlation/sequence、redaction、unknown usage、metrics aggregation、dataset version、budgeted judge。
- 集成测试：fake Run/Invocation/Event 端到端写入 Trace/metrics，断线补拉和 cancel/success 状态一致；越权/qB unauthorized 不产生 external call。
- 回归测试：`cd backend && uv run pytest tests/trace tests/evaluation tests/harness tests/acceptance -q`。
- CI 验证：运行现有 backend test command 和 frontend `pnpm vitest run`；检查失败时 gate 返回非零且报告不含 secrets。
- 手工验证：查看一条成功、失败、取消和 policy denied Run 的 report，确认可以按 run_id/sequence 解释且无 raw Prompt/CoT。

## 验收标准

- [ ] Trace、Event、Metrics 使用同一 Run/Invocation 标识和 sequence。
- [ ] 安全/恢复/成本/延迟/Tool selection/Policy Eval 有可重复 baseline。
- [ ] secret、raw Prompt、CoT、完整 Tool output 不进入日志、Trace、Eval report。
- [ ] 相关代码变更能触发对应 Eval/CI gate，fake provider 下可运行。
- [ ] 不改变业务行为、DB migration、前端协议或现有 Eval CLI 兼容性。

## 回滚

关闭新增 metrics/CI gate 的 report projection，保留旧 Trace/Eval 读路径和历史 baseline；不得通过取消 redaction 或删除失败样本回滚。若某指标不稳定，只降低其为观察指标，不删除安全/恢复 gate。

## 输出

- 修改文件列表：记录 Trace/Eval/metrics/CI 和测试。
- 测试结果：报告各 dataset version、metric、gate、fake provider 结果。
- 未解决问题：记录真实 provider 费用价格、OpenTelemetry/生产 metrics backend 的部署选择。
- 风险说明：说明 Eval judge 非确定性和 usage unknown 对成本估计的影响。
