# 推荐候选渐进式召回实施计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前会话中按任务执行，并在每个检查点运行验证。

**目标：** 修复推荐候选召回过严导致的错误兜底：每个偏好标签独立召回、扩大候选池、合并排序，并仅硬过滤明确反感标签。

**范围：** `backend/app/agents/recommendation_agent.py`、`backend/app/services/user_profile_service.py` 及对应测试；不修改数据库 schema，不修改前端。

### 任务 1：画像输出强反感标签

**文件：**
- 修改：`backend/app/services/user_profile_service.py`
- 测试：`backend/tests/services/test_user_profile_service.py`

- [ ] **步骤 1：编写失败测试**

新增测试验证：低于中心基准但样本不足的标签不进入 `strong_avoid_tags`；达到负向阈值且样本量足够的标签进入；`动画`、`TV`、`WEB`、`OVA`、`OAD`、`剧场版` 和纯年份标签不进入强反感集合。

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/services/test_user_profile_service.py -q`

预期：新增字段不存在或断言失败。

- [ ] **步骤 3：实现最小改动**

在画像生成阶段基于 `preference_delta <= -0.6`、`weighted_count >= 3.0` 和结构性标签判断生成 `strong_avoid_tags`，保留已有 `avoid_tags` 兼容字段。

- [ ] **步骤 4：运行测试确认通过**

运行：`pytest tests/services/test_user_profile_service.py -q`

预期：PASS。

### 任务 2：多路召回与候选合并

**文件：**
- 修改：`backend/app/agents/recommendation_agent.py`
- 测试：`backend/tests/agents/test_recommendation_agent.py`

- [ ] **步骤 1：编写失败测试**

新增测试验证：前三个偏好标签各触发一次单标签搜索且 `keyword` 为空；每次使用扩大后的 limit；结果按 ID 去重；单路失败不阻断其他成功结果；已看和 `strong_avoid_tags` 仍被过滤；普通 `avoid_tags` 只影响排序；所有搜索失败才返回 `candidate_search_failed`。

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/agents/test_recommendation_agent.py -q`

预期：当前实现只调用一次搜索，并且把多个标签作为“且”条件。

- [ ] **步骤 3：实现最小改动**

在 `RecommendationAgent` 中提取召回量常量，逐标签调用 capability，聚合成功结果，按 subject ID 去重；保存每个候选的首次召回顺序；计算偏好匹配分、普通负偏好惩罚和 Bangumi 评分后排序。

- [ ] **步骤 4：运行测试确认通过**

运行：`pytest tests/agents/test_recommendation_agent.py -q`

预期：PASS。

### 任务 3：准确空结果语义和 trace 统计

**文件：**
- 修改：`backend/app/agents/recommendation_agent.py`
- 测试：`backend/tests/agents/test_recommendation_agent.py`

- [ ] **步骤 1：编写失败测试**

新增测试区分冷启动、所有搜索失败、搜索成功但原始结果为空、原始结果存在但全部被过滤四种 evidence reason，并验证召回和过滤计数可供响应/trace 使用。

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/agents/test_recommendation_agent.py -q`

预期：当前实现把空候选统一视作普通兜底，且没有阶段统计。

- [ ] **步骤 3：实现最小改动**

让候选选择器返回候选和统计信息；将搜索失败与过滤后为空分开处理；在 capability/agent trace 边界记录不含收藏正文的聚合计数。

- [ ] **步骤 4：运行测试确认通过**

运行：`pytest tests/agents/test_recommendation_agent.py -q`

预期：PASS。

### 任务 4：回归验证

- [ ] 运行推荐相关测试：`pytest tests/agents/test_recommendation_agent.py tests/services/test_user_profile_service.py tests/capabilities -q`
- [ ] 运行全部后端测试：`pytest -q`
- [ ] 运行 Ruff：`ruff check app tests`
- [ ] 运行格式检查：`git diff --check`
- [ ] 检查当前用户画像场景：99 条收藏、68 条评分时不再进入 cold-start 兜底；若外部 Bangumi 服务可用，至少返回一个未看且不命中强反感标签的候选。

## 提交边界

实现提交只包含本计划涉及的后端代码和测试；保留工作区中已有的认证、数据库会话兼容等改动，不进行 reset、checkout 或清理。
