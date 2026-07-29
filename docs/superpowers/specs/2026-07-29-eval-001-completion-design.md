# EVAL-001 完善设计

## 目标

建立可重复、默认离线、能够阻止回归的 Agent 评测闭环。Fast 模式必须
通过现有 `AgentRuntime` 执行确定性 Adapter，不访问网络；Full 模式复用
同一协议，可注入真实 Agent 和可选模型 Judge。

## 架构

评测系统分为六个边界清晰的组件：

1. `types.py` 定义严格的数据集、执行结果、指标、配置和报告类型。
2. `dataset.py` 加载带显式版本的 JSONL，用例包含用户/记忆 fixtures、
   assertions、期望路由、能力约束和 tags。
3. `adapter.py` 将评测用例转换为 `AgentTask`，通过 `AgentRuntime` 运行
   Adapter。Fast Adapter 读取用例 fixtures 生成确定性事件；Full 模式可
   注入生产 Agent Adapter。
4. `metrics.py` 计算路由、schema、能力约束、事实证据、恢复、安全、
   延迟和调用预算指标。
5. `judge.py` 定义异步 Judge 协议，显式表达 available/unavailable，
   强制超时，并用包含 provider/model/rubric/config 的内容哈希缓存。
6. `runner.py` 解析严格 YAML 配置、过滤用例、执行并隔离失败、聚合指标、
   比较 baseline、输出终端与 JSON 报告，并按配置阈值决定退出码。

## Fast 与 Full

- Fast：无密钥、无网络，运行真实 `AgentRuntime` 生命周期和确定性 Adapter。
  数据集中的 `fixtures.result` 是 provider/tool double 的输入，而不是绕过
  Runner 的预计算通过结果。
- Full：通过依赖注入装配真实 Agent 和 Judge。Judge 不可用、超时或解析失败
  都写入报告，不能静默视为通过。

## 配置与门禁

YAML 配置严格校验 dataset、tags、thresholds、报告路径、baseline、预算和
Judge 配置。阈值支持 `min`/`max` 方向；缺失必需指标视为失败。CLI 的退出码
仅由配置阈值、baseline 回归和必需 Judge 状态共同决定，而不是要求每个非必需
指标均为 100%。

## 报告与 Baseline

报告包含 dataset 版本、配置名、任务、Agent、模型/provider、Git revision、
起止时间、逐用例执行和指标、聚合指标、Judge 状态以及门禁失败原因。JSON
使用稳定 schema。Baseline 显式版本化，逐指标记录方向、期望值、容差和
required；禁止隐式覆盖。

## CI

GitHub Actions 在 PR/push 上运行单元测试、Ruff 和 Fast gate，并上传 JSON
报告；scheduled/manual job 执行 Full gate，使用 protected secrets，限制
并发和预算，且不打印 provider 原始响应。

## 错误处理

- 单个用例异常转成失败结果，其余用例继续。
- 配置、数据集或报告 schema 无效时快速失败并给出路径上下文。
- Judge 超时/不可用显式记录。
- 报告只保存评测字段，不保存 provider 原始响应或密钥。

## 测试策略

先为每个缺失行为编写失败测试，再实现最小代码：

- 数据集版本、fixtures、assertions 和覆盖类别。
- 配置解析、tags、阈值边界和无效配置。
- `AgentRuntime` 执行、用例隔离、部分失败和预算。
- 每项确定性指标及边界。
- Judge 解析、缓存隔离、超时和不可用。
- Baseline 改进、容差、回归和指标方向。
- CLI 退出码、JSON schema 和 Git revision。
- Fast 命令、Ruff 和全量测试。
