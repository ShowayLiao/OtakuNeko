# Service Capability 接入实施计划

> **面向 AI 代理的工作计划**：本计划用于后续按阶段执行。每个阶段都必须先补失败测试，再实现最小改动，并在阶段结束后运行相关回归。当前不创建新的 Harness Batch execution record；只有获得明确的 Batch 执行授权后，才将对应阶段映射到活动 Batch。

**目标：** 将当前 `backend/app/services/` 中可供当前用户使用的数据能力接入统一 Capability Registry、Runtime Dispatcher 和审批边界，使 AI 可以读取当前用户的完整业务数据，并能提出日程/收藏等写操作，在系统判定为风险操作后暂停等待前端确认。

**核心方案：** 按数据域而不是按 Service 文件建立 Capability。Service 继续负责领域逻辑；Capability 负责公开 Schema、权限、风险、幂等和结果边界；Runtime 负责注入 `user_id`、`db`、租户和审批上下文。模型只能提交业务字段，不能提交身份、数据库、凭据或资源归属字段。

**技术栈：** Python、FastAPI、Pydantic、SQLModel/SQLAlchemy、Capability Registry、Dispatcher、`CapabilityAdapter`、`SqlIdempotencyStore`、现有 Run/Event/Approval 契约。

---

## 一、当前事实与边界

当前 `/chat` 已经构建 Capability Registry、Dispatcher 并调用 `AgentRuntime.stream_decision()`：

- `backend/app/api/v1/agent.py:427-540`
- `backend/app/capabilities/factory.py:11-18`

当前已注册的 Capability 是 Anime、Recommendation、Schedule、Media、System。`agents/tools/` 是兼容包装层，不作为新增 Service 接入的主要入口。

当前 Service 接入状态：

| Service | 目标接入方式 | 处理结论 |
|---|---|---|
| `bangumi_service.py` / `bangumi_client.py` | 扩展 Anime/Bangumi Capability | 保留现有详情、搜索、制作人员、声优、评价；补日历和受控用户信息 |
| `user_profile_service.py` | Recommendation Capability | 保留画像/偏好；画像数据改为服务端按当前用户读取 |
| `collection_service.py` | 新增 Collection Capability | 补齐当前用户收藏读写；不允许模型传 `user_id` |
| `subject_service.py` | 新增 Subject Capability | 默认只读本地/混合条目数据；全局写入不进入普通 Agent |
| `schedule_service.py` | 扩展 Schedule Capability | 支持读取、创建、修改、删除、按日查询和同步；写入统一审批 |
| `stats_service.py` | 新增 Stats Capability | 只读当前用户统计数据 |
| `douban_service.py` | Collection Capability 的同步动作 | 写入数据库，必须显式审批和审计 |
| `qb_service.py` | 完善 Media Capability | 读取和写入 qBittorrent RSS/规则；高风险、用户 allowlist、审批 |
| `bangumi_data_sync.py` | 作为内部实现 | 不独立暴露给模型，由日程/条目能力调用 |
| `user_service.py` | 仅提供受限 Account Capability（可选） | 禁止普通 Agent 使用全量用户、登录、删除和管理员 CRUD |

非目标：

- 不创建“数据库查询”或“全部 Service 方法”通用工具。
- 不向模型暴露 `AsyncSession`、HTTP Client、qBittorrent 凭据、JWT、BYOK 或原始 Provider payload。
- 不允许 AI 选择其他用户的 `user_id`、收藏、日程或统计数据。
- 不把副作用动作伪装成只读动作；写操作必须保留审批、超时、取消、幂等和审计边界。

---

## 二、Capability 目标目录

### Capability A：CollectionCapability

**实现文件：**

- 新建：`backend/app/capabilities/collections.py`
- 修改：`backend/app/capabilities/factory.py`
- 复用：`backend/app/services/collection_service.py`
- 复用：`backend/app/services/bangumi_service.py`
- 复用：`backend/app/services/douban_service.py`

**公开只读动作：**

- `list_collections`
- `get_collection`
- `search_collections`

**审批写动作：**

- `create_collection`
- `update_collection`
- `delete_collection`
- `upsert_collection`
- `batch_upsert_collections`
- `import_json_collections`
- `sync_bangumi_collections`
- `sync_douban_collections`

**实现要求：**

1. 公开 Schema 不包含 `user_id`、数据库会话、缓存句柄或外部凭据。
2. `CapabilityAdapter` 通过可信上下文注入当前 `user_id` 和 `db`。
3. 所有查询必须调用当前用户范围的 Service 方法；不得接受模型提供的用户范围过滤器作为授权依据。
4. 写动作声明 `is_side_effect=True`、`approval_required=True`、`idempotency_mode="required"`。
5. 同步和批量导入必须返回结构化计数、失败项摘要和人工复核状态，不返回完整原始外部 payload。

**测试：**

- 新建：`backend/tests/capabilities/test_collections.py`
- 修改：`backend/tests/harness/test_capability_adapter.py`
- 修改：`backend/tests/harness/test_dispatcher.py`
- 修改：`backend/tests/acceptance/test_capability_boundary.py`

必须覆盖当前用户隔离、伪造 `user_id` 拒绝、只读查询、无审批暂停、批准写入、拒绝不写入、幂等冲突和批量部分失败。

### Capability B：SubjectCapability

**实现文件：**

- 新建：`backend/app/capabilities/subjects.py`
- 修改：`backend/app/capabilities/factory.py`
- 复用：`backend/app/services/subject_service.py`
- 复用：`backend/app/services/bangumi_client.py`

**公开只读动作：**

- `get_subject`
- `search_local_subjects`
- `search_remote_subjects`
- `search_mixed_subjects`
- `get_subject_air_time`

**权限边界：**

- 条目详情和搜索作为只读能力提供给 Agent。
- `create_subject`、`update_subject`、`delete_subject`、批量写入不进入普通用户 Agent allowlist。
- `sync_subject_air_time` 若会修改本地缓存，按内部同步或低风险受控动作处理，不直接暴露原始同步接口。

**测试：**

- 新建：`backend/tests/capabilities/test_subjects.py`
- 复用：`backend/tests/capabilities/test_anime.py`
- 修改：`backend/tests/acceptance/test_capability_boundary.py`

### Capability C：Anime/Bangumi 扩展

**修改文件：**

- `backend/app/capabilities/anime.py`
- `backend/app/services/bangumi_service.py`
- `backend/app/services/bangumi_client.py`

**新增动作：**

- `get_bangumi_calendar`
- `get_bangumi_user_info`

其中 `get_bangumi_user_info` 默认只允许查询当前已绑定的 Bangumi 身份；若要支持公开用户名搜索，必须单独命名为公开数据动作，不能将任意用户名视为当前用户身份。

**测试：**

- 修改：`backend/tests/capabilities/test_anime.py`
- 新建或修改：`backend/tests/capabilities/test_bangumi.py`
- 退役手工脚本：原 `backend/test_anime_staff_cast.py` 已移除；相关回归统一收敛到 `backend/tests/capabilities/test_anime.py`

### Capability D：Schedule 扩展与审批接口

**修改文件：**

- `backend/app/capabilities/schedule.py`
- `backend/app/api/v1/agent.py`
- `backend/app/api/v1/endpoints/schedules.py`
- `backend/app/harness/capability_adapter.py`（仅在可信依赖工厂需要补充时修改）
- `backend/app/capabilities/registry.py`

**只读动作：**

- `list_schedules`
- `list_schedules_by_day`
- `list_unified_schedules`

**审批写动作：**

- `create_schedule`
- `update_schedule`
- `delete_schedule`
- `upsert_schedule`
- `bulk_upsert_schedules`
- `sync_bangumi_schedule`

`delete_all_schedules` 默认不进入普通 Agent allowlist，即使保留后端接口，也要求更高角色或显式人工确认。

**关键实现：**

1. `/chat` 构造 Dispatcher 时通过 `adapter_factory` 注入 `trusted_args={"db": db}`，解决当前聊天路径调用 Schedule Service 缺少数据库会话的问题。
2. `user_id` 由 `ExecutionContext.principal_id` 注入，不出现在公开参数 Schema。
3. 写动作向模型公开“需要审批”的描述和风险级别，但没有审批时不能执行。
4. Dispatcher 返回 `approval_required` 事件，包含 `approval_id`、动作名、风险级别和安全的参数摘要。
5. 前端暂不必本轮实现 UI；后续使用现有 `/chat/resume` 以 `approve/reject` 继续或终止 Run。
6. 所有写动作要求前端或 Runtime 提供幂等键；重复请求必须返回原执行结果或冲突，不得重复写入。

**测试：**

- 修改：`backend/tests/capabilities/test_schedule.py`
- 修改：`backend/tests/harness/test_capability_adapter.py`
- 修改：`backend/tests/harness/test_dispatcher.py`
- 修改：`backend/tests/harness/test_api_regression.py`
- 修改：`backend/tests/api/test_collections_idempotency.py`（作为幂等测试模式参考）

必须覆盖：AI 提议写入、无审批暂停、批准执行、拒绝执行、跨用户访问拒绝、幂等重试、取消、超时和数据库依赖注入。

### Capability E：StatsCapability

**实现文件：**

- 新建：`backend/app/capabilities/stats.py`
- 修改：`backend/app/capabilities/factory.py`
- 复用：`backend/app/services/stats_service.py`

**公开动作：**

- `get_user_stats`

统计服务只允许读取当前用户的统计结果。输出应限制为 Dashboard 所需的结构化统计，不返回 SQL、缓存键、其他用户计数或内部异常。

**测试：**

- 新建：`backend/tests/capabilities/test_stats.py`
- 修改：`backend/tests/acceptance/test_capability_boundary.py`

### Capability F：Recommendation 数据来源收口

**修改文件：**

- `backend/app/capabilities/recommendation.py`
- `backend/app/agents/recommendation_agent.py`
- `backend/app/api/v1/agent.py`
- `backend/tests/capabilities/test_recommendation.py`
- `backend/tests/agents/test_recommendation_agent.py`

**实现要求：**

1. `generate_profile` 和 `analyse_taste` 的公开输入不再把完整 `collections` 列表交给模型自由构造。
2. Capability 通过可信 `db` 和 `principal_id` 读取当前用户收藏，或由 Runtime 注入可信的只读收藏快照。
3. `RecommendationAgent` 不再依赖 API 层直接把收藏列表塞入普通模型可见 metadata。
4. 画像输出保留 evidence，但限制条目、标签、摘要和 payload 大小。

这样既能让 AI 使用当前用户的完整画像数据，也避免模型伪造或混入其他用户收藏。

### Capability G：Media/QBittorrent

**修改文件：**

- `backend/app/capabilities/media.py`
- `backend/app/services/qb_service.py`
- `backend/app/api/v1/rss.py`（只在需要复用授权/错误契约时修改）
- `backend/tests/capabilities/test_media.py`
- `backend/tests/api/test_rss_idempotency.py`

**只读动作：**

- `library_status`
- `list_rss_feeds`
- `list_rss_rules`

**高风险审批动作：**

- `add_rss_feed`
- `upsert_rss_feed`
- `remove_rss_feed`
- `set_rss_rule`
- `remove_rss_rule`

所有动作必须复用 qB allowlist、用户认证、幂等、超时、审计和未知结果处理。任何 qB 凭据只从服务端配置读取，不能出现在 Action Schema、Trace 或 SSE。

### Capability H：受限 AccountCapability（最后实施）

**可选实现文件：**

- 新建：`backend/app/capabilities/account.py`
- 复用：`backend/app/services/user_service.py`
- 修改：`backend/app/capabilities/factory.py`

**仅允许：**

- `get_my_profile`
- 经过字段 allowlist 的 `update_my_profile`

**禁止：**

- `get_all_users`
- 任意 `get_user_by_id`
- `create_user`
- `login_user`
- `delete_user`
- 角色、权限、密码、Token、BYOK 和管理员字段修改

---

## 三、统一 Registry、Schema 与 Runtime 注入

### 任务 1：扩展 Capability Registry 的动作发现模式

**文件：**

- `backend/app/capabilities/registry.py`
- `backend/app/capabilities/types.py`
- `backend/app/api/v1/agent.py`
- `backend/tests/capabilities/test_registry.py`

当前 `allowed_public_definitions()` 会过滤副作用动作。需要增加显式的 `include_side_effects` 或等价入口：

- 匿名 Run：仅公开只读动作。
- 已认证 Run：可发现审批写动作，但动作定义必须带 `approval_required`、`risk_level`、`idempotency_mode`。
- Dispatcher 仍然是唯一执行边界；让动作“可发现”不等于允许绕过 Policy 执行。

### 任务 2：统一可信依赖工厂

**文件：**

- `backend/app/api/v1/agent.py`
- `backend/app/harness/capability_adapter.py`
- `backend/app/harness/dispatcher.py`
- `backend/tests/harness/test_capability_adapter.py`

建立当前 Agent Run 使用的 Adapter 工厂，注入：

- `user_id`：来自 `ExecutionContext.principal_id`，不可由模型覆盖。
- `db`：来自 FastAPI 请求依赖，不进入 Schema。
- 幂等存储：来自当前持久化配置。
- 审批对象：只来自 Runtime/前端 resume，不来自模型参数。

对模型参数执行 runtime-owned field 拒绝测试，确保 `user_id`、`tenant_id`、`db`、`approval`、凭据等字段不能伪造。

---

## 四、审批与前端交互契约

后端先完成契约，前端 UI 可后续实现。

### 审批暂停事件

建议事件结构：

```json
{
  "type": "approval_required",
  "run_id": "run-id",
  "approval_id": "approval-id",
  "capability": "create_schedule",
  "capability_version": "v1",
  "risk_level": "high",
  "argument_keys": ["source", "source_id", "day_of_week", "start_time"],
  "safe_arguments": {
    "source": "bangumi",
    "source_id": "12345",
    "day_of_week": 2,
    "start_time": "20:00:00"
  }
}
```

禁止返回：用户 Token、qB 凭据、数据库信息、完整原始 Provider payload、未裁剪的外部文本。

### Resume 行为

- `approve`：使用服务端保存的 pending Decision 继续 Dispatcher 执行。
- `reject`：写入拒绝事件，Run 进入可审计的终止状态，不调用 Service。
- 超时、取消、服务重启：不能自动批准；应恢复为 paused、cancelled 或 manual review。

现有入口：`backend/app/api/v1/agent.py:658-793`。需补充真实写操作和 API fake-provider 回归测试。

---

## 五、实施阶段与检查点

### 阶段 0：契约与基线

- 固定 Capability action 名称、版本、输入/输出 Schema、风险和幂等语义。
- 增加 Registry 可发现副作用动作但不执行的失败测试。
- 增加跨用户、身份伪造、无审批写入失败测试。
- 运行后端 Harness/Capability 相关测试并记录基线。

**检查点：** 未完成身份注入和审批失败测试，不进入业务 Service 接入。

### 阶段 1：只读用户数据

按顺序接入：

1. CollectionCapability：收藏列表、详情、搜索。
2. SubjectCapability：本地和混合条目搜索、详情。
3. StatsCapability：当前用户统计。
4. Schedule 只读扩展：按日和统一日程。
5. Anime/Bangumi 日历和受控用户信息。

**检查点：** AI 能读取当前用户全部主要业务数据；跨用户查询、模型传入 `user_id`、未授权访问均被拒绝。

### 阶段 2：推荐数据来源收口

- 让 Recommendation Capability 内部读取可信收藏数据。
- 移除 API 层向模型 metadata 直接注入完整收藏列表的依赖。
- 保持 RecommendationAgent 通过 Runtime Dispatcher 调用 Anime/Recommendation Capability。

**检查点：** 画像只基于当前用户数据，模型不能伪造收藏样本。

### 阶段 3：日程写入和审批

- 修复 `/chat` 的 `db` trusted dependency 注入。
- 开放认证 Run 的审批写动作目录。
- 实现 `approval_required`、`/chat/resume`、幂等和拒绝终止。
- 先覆盖 `create_schedule`、`update_schedule`、`delete_schedule`。

**检查点：** 无审批不写库；批准只执行一次；拒绝、取消、超时均无隐式写入。

### 阶段 4：收藏写入和外部同步

- 接入收藏 CRUD、批量写入和手动导入。
- 接入 Bangumi/Douban 同步。
- 明确同步部分成功、补偿、未知结果和人工复核。

**检查点：** 重试不会重复创建；外部同步凭据不进入模型和日志；部分成功有结构化结果。

### 阶段 5：qBittorrent Media Capability

- 将 Media 占位实现替换为 QBService adapter。
- 先接只读 RSS/规则查询，再接写入。
- 复用 qB allowlist、审批和幂等策略。

**检查点：** 未授权用户不能发现或调用 qB 写能力；网络/Provider 错误不会盲目重试副作用。

### 阶段 6：受限账户和管理员边界

- 如确有需求，再接 `get_my_profile` 和字段 allowlist 的自助更新。
- 不把完整 `UserService` 暴露给普通 Agent。
- 管理员能力另建角色和 allowlist，不与普通聊天 Capability 混用。

---

## 六、验证矩阵

每个阶段至少运行：

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
```

阶段内需要缩小范围时，从仓库根目录使用：

```powershell
uv run --directory backend pytest tests/capabilities tests/harness
uv run --directory backend pytest tests/acceptance/test_capability_boundary.py tests/harness/test_api_regression.py
```

完整验收包括：

- 只读动作的 Schema、结果大小和字段脱敏。
- 当前用户读取成功，其他用户读取拒绝。
- AI 传入 `user_id`、`db`、审批字段被拒绝。
- 日程写入无审批暂停，批准执行，拒绝不执行。
- 幂等重试、冲突、超时、取消和未知外部结果。
- qB 用户 allowlist、凭据脱敏和高风险写入审批。
- Fast Eval、Observability Eval、后端全量测试和 Ruff。
- `git diff --check`、完整未提交 diff Review。

---

## 七、回滚与发布策略

- 每个阶段独立注册新 Capability；旧 REST Service 保留不删除。
- 新 Capability 通过 allowlist/feature flag 控制发现，不通过删除旧代码回滚。
- 只读能力可先默认开启；写能力先保持审批门控和认证用户限定。
- qB、外部同步和账户能力默认关闭，完成真实 API/fake-provider 回归后再逐项开启。
- 发现未知副作用时停止自动重试，进入人工复核或补偿路径。
- 未经明确授权不创建 Batch execution record、不提交、不部署、不运行生产迁移。

---

## 八、计划自检

- [x] 覆盖当前 Service 的数据域和不应暴露的内部服务。
- [x] 明确 AI 修改日程的接口、审批暂停和前端 resume 契约。
- [x] 明确 `user_id` 可由 Runtime 注入但不能由模型传入。
- [x] 明确 db、凭据和外部客户端的可信注入边界。
- [x] 每个新增 Capability 都有实现文件、Service 依赖和测试路径。
- [x] 写操作有审批、幂等、超时、取消和审计要求。
- [x] 计划不要求删除旧 Service 或绕过 Dispatcher。
- [x] 计划阶段可独立验收和回滚。
