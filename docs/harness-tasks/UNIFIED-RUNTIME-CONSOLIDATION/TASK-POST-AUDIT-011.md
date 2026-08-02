# TASK-POST-AUDIT-011：ModelGateway Cancellation、Timeout 与 Provider Error Hardening

## 目标

把模型调用纳入 Runtime 可控制、可取消、可计量的统一边界，确保 Provider adapter 不吞掉任务取消，且模型调用的 cancelled、timeout、provider failure 不会被错误映射为成功或普通解析失败。

本任务不负责切换 /chat 默认路径，也不负责删除 LangGraph；它为 TASK-007 和 TASK-010 提供可靠的 ModelGateway contract。

## 当前缺口

- backend/app/harness/model_gateway.py 的 Provider adapter 存在 except BaseException 路径。
- ModelGateway.infer() 的公开契约没有显式接收 CancellationToken、deadline 或 model-call budget。
- AgentRuntime.stream_decision() 通过 DecisionParseError 处理 provider cancelled 时，可能把 ErrorCode.CANCELLED 写成 run_failed。
- 模型调用期间没有与 Tool Dispatcher 等价的可取消等待和任务回收规则。

## 依赖与允许范围

### 依赖

- TASK-POST-AUDIT-006 的 Runtime-owned Decision Loop contract。
- 现有 CancellationToken、RunBudget、ModelCallResult、ErrorCode 和 provider adapter。

### 允许修改

- backend/app/harness/model_gateway.py
- backend/app/harness/model_types.py
- backend/app/harness/budget.py
- backend/app/harness/runtime.py
- backend/app/harness/coordinator.py
- backend/tests/harness/
- backend/tests/acceptance/
- 对应 execution record

### 禁止修改

- 不在本任务切换主 API 默认 feature flag。
- 不删除 LangGraph compatibility adapter。
- 不改变 provider SDK 依赖或升级无关依赖。
- 不记录 API key、完整 prompt、raw provider payload 或 raw exception。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. 模型请求执行期间触发 CancellationToken.cancel()，Provider task 被取消，Runtime 只产生一个 run_cancelled terminal event。
2. 模型 deadline 到期时，Provider task 被回收，Runtime 只产生一个 run_timeout terminal event。
3. Provider 返回 cancelled result 时，Parser/Runtime 保留 ErrorCode.CANCELLED，不能降级为 failed。
4. Provider 抛出 asyncio.CancelledError 时不被普通 BaseException handler 吞掉。
5. Provider transient/permanent error 的 retryable、terminal 和 safe error category 保持稳定。
6. cancellation、timeout 和 provider error 不会触发下一轮 Decision 或 Dispatcher invocation。
7. RunBudget 的 model-call、step 和 deadline 预算在取消/超时后不会被重复扣减。
8. Gateway close/recovery 不会遗留未等待的 asyncio task。

## 实现要求

### 1. 明确 ModelGateway contract

ModelGateway.infer() 至少接受以下 provider-neutral 输入：

~~~text
goal
messages
run_id
trace_id
context snapshot
cancellation token
deadline / remaining timeout
budget metadata
~~~

Provider SDK 对象、HTTP client、凭据和 raw response 只能停留在 adapter 内部。

### 2. 统一任务控制

参考 Dispatcher._run_with_controls() 的竞速语义，但不要复制成第二套随意实现。模型调用必须：

- 监听 cancellation event；
- 按剩余 Run deadline 设置最大等待时间；
- 取消后等待 Provider task 收尾；
- 明确区分 caller cancellation、Run deadline、provider timeout 和 provider failure；
- 不将取消当作可重试普通错误。

### 3. 保留安全错误

对外只暴露结构化 error code/category、retryable、usage、latency、provider/model 标识；禁止把 raw provider exception、token、完整请求或响应写入 Event、Trace、SSE、Memory 或 Eval fixture。

### 4. Runtime terminal 映射

Runtime 必须在模型边界和 Parser 边界都保持如下映射：

~~~text
cancelled       -> run_cancelled / ErrorCode.CANCELLED
deadline        -> run_timeout / ErrorCode.TIMEOUT
budget          -> budget_exceeded terminal
provider error  -> run_failed / safe provider code
~~~

同一个 Run 只能产生一个 terminal event，不能在 cancelled 后继续解析 Decision 或调用 Dispatcher。

## 验收

- focused model gateway/cancellation tests 先失败后通过；
- 后端全量测试和 Ruff 通过；
- Runtime acceptance 覆盖模型进行中取消、超时、provider failure 和 no-next-invocation；
- Fast Eval 与 observability Eval 通过；
- git diff --check 通过；
- Review verdict 为 pass，无未处理 High/Medium finding。

## 回滚

保留旧 provider-neutral adapter 和已有 compatibility projection；如新 cancellation contract 不能满足某个 provider，只能显式回到已验证的 adapter，并把该 provider 标记为不可用或 single-worker compatibility，不得吞掉取消或伪造成功。
