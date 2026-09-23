# Bangumi 日历详情编排实现计划

> **面向实现者：** 使用 TDD 执行本计划；每一步先运行对应的定向测试，再进入下一步。

**目标：** 确保 Bangumi 日历使用新鲜且完整的七天数据，并让“本周值得关注新番”在最终回答前按日历中的 subject ID 补查有限数量的作品详情。

**边界：** 只修改后端 Bangumi service、anime capability、模型工作流提示和回归测试；不修改前端流式渲染，不为全部日历条目无界地抓取详情。

**方案：** 日历缓存升级到新命名空间；新增最多 5 个 subject ID 的批量详情只读能力；当日历与批量详情能力同时可用时，向模型注入明确的“日历 → 选候选 ID → 批量详情 → 最终回答”工作流约束。

### 任务 1：锁定完整日历和缓存回退行为

**文件：**
- 修改：`backend/app/services/bangumi_client.py`
- 修改：`backend/app/services/bangumi_service.py`
- 测试：`backend/tests/services/test_bangumi_client.py`
- 测试：`backend/tests/services/test_bangumi_service.py`

- [ ] 增加 service 回归测试：不接受只包含部分 weekday 的日历结果。
- [ ] 运行测试确认当前实现无法满足完整日历约束。
- [ ] 将日历缓存命名空间升级，避免旧的单日缓存继续命中。
- [ ] 保留已有 API/网页回退，并在 service 边界校验七个 weekday ID。
- [ ] 运行定向测试确认完整日历通过、部分日历被拒绝。

### 任务 2：增加有界的批量详情能力

**文件：**
- 修改：`backend/app/services/bangumi_service.py`
- 修改：`backend/app/capabilities/anime.py`
- 测试：`backend/tests/services/test_bangumi_service.py`
- 测试：`backend/tests/capabilities/test_anime.py`

- [ ] 增加失败测试：批量能力应按传入 ID 获取详情、去重并保留失败 ID；超过 5 个 ID 必须拒绝。
- [ ] 使用并发的既有 `fetch_subject_by_id()` 获取 `summary`、评分、制作人员和声优，避免重复实现详情清洗。
- [ ] 注册只读 `get_anime_info_batch` action，输入为 1–5 个 `subject_ids`。
- [ ] 返回结构化 `details` 和 `failed_subject_ids`，不把外部异常原文暴露给模型。
- [ ] 运行 service/capability 定向测试确认边界和错误结果。

### 任务 3：强制日历分析的后续查询工作流

**文件：**
- 修改：`backend/app/capabilities/anime.py`
- 修改：`backend/app/harness/model_gateway.py`
- 测试：`backend/tests/harness/test_model_gateway.py`
- 测试：`backend/tests/harness/test_runtime_orchestration.py`

- [ ] 增加失败测试：模拟模型先调用日历，再调用批量详情，最后回答；断言详情调用确实发生且使用日历 ID。
- [ ] 在 capability 描述中说明日历摘要可能为空，批量详情必须用于候选作品分析。
- [ ] 仅当相关 Bangumi 能力存在时注入工作流提示，要求模型不能在日历结果后直接终止回答。
- [ ] 运行 gateway prompt 和 Runtime 调用序列测试确认工作流契约可观察。

### 任务 4：完整验证

**文件：**
- 无新增业务文件。

- [ ] 运行 `uv run --directory backend --no-cache pytest -q`。
- [ ] 运行 `uv run --directory backend --no-cache ruff check app tests`。
- [ ] 运行 `git diff --check` 并复核完整未提交 diff，确认没有改动流式渲染或无关文件。
