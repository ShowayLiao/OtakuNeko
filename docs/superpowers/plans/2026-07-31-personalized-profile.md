# 个性化用户画像优化实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用评分中心化、时间衰减和小样本平滑增强用户画像，并让推荐候选优先匹配喜欢标签、避开回避标签。

**架构：** `user_profile_service` 负责纯统计画像和兼容输出；`RecommendationAgent` 负责把画像转成搜索参数、过滤候选。画像函数通过可选 `as_of` 参数获得可测试的时间基准，生产调用保持默认行为。

**技术栈：** Python 3.11、pytest/pytest-asyncio、Pydantic schema、现有 Bangumi capability。

---

### 任务 1：为增强画像建立失败测试

**文件：**
- 创建：`backend/tests/services/test_user_profile_service.py`
- 参考：`backend/app/services/user_profile_service.py`

- [ ] **步骤 1：编写失败测试**

添加最小的 `SimpleNamespace` fixtures，覆盖以下行为：

```python
def test_profile_shrinks_personal_baseline_toward_neutral_prior():
    profile = generate_user_profile([rated_item(10, tags=[])] , as_of=AS_OF)
    assert profile["llm_summary"]["rating_baseline"] == pytest.approx(7.5)


def test_recent_rating_has_more_influence_than_old_rating():
    profile = generate_user_profile(
        [rated_item(10, days_ago=0), rated_item(2, days_ago=365)],
        as_of=AS_OF,
    )
    assert profile["llm_summary"]["rating_baseline"] > 7.0


def test_tags_are_classified_by_centered_preference():
    profile = generate_user_profile(tagged_items_for_liked_and_avoided_tags(), as_of=AS_OF)
    summary = profile["llm_summary"]
    assert "喜欢" in summary["favorite_tags"]
    assert "雷区" in summary["avoid_tags"]


def test_legacy_profile_fields_remain_available():
    profile = generate_user_profile(tagged_items_for_liked_and_avoided_tags(), as_of=AS_OF)
    assert set(("total_rated", "taste_dictionary")) <= profile["llm_summary"].keys()
    assert set(("radar", "bar_count", "bar_score")) <= profile["chart_data"].keys()
```

Fixtures must give `subject.tags` as `[{"name": tag}]`, `item.rate` as an integer, and `item.updated_at` as UTC datetimes. Include one rated item without tags to prove it affects the baseline.

- [ ] **步骤 2：运行测试确认正确失败**

运行：

```text
Set-Location backend
uv run pytest tests/services/test_user_profile_service.py -q
```

预期：FAIL，原因是 `generate_user_profile` 尚不接受 `as_of`，且输出没有 `rating_baseline`、`favorite_tags` 和 `avoid_tags`。

- [ ] **步骤 3：提交测试**

```text
git add backend/tests/services/test_user_profile_service.py
git commit -m "test: specify personalized profile scoring"
```

### 任务 2：实现画像算法

**文件：**
- 修改：`backend/app/services/user_profile_service.py:44-323`
- 测试：`backend/tests/services/test_user_profile_service.py`

- [ ] **步骤 1：扩展输入清洗**

保留 `watched_ids` 逻辑，同时将所有有评分的记录保存为 baseline entries；带标签记录继续保存为 tag entries。每条 entry 携带 `score`、`tags` 和 `updated_at`。无时间戳权重为 `1.0`，异常时间戳也回退为 `1.0`。

- [ ] **步骤 2：实现时间权重和评分基准**

增加常量：

```python
_NEUTRAL_SCORE = 7.0
_BASELINE_PRIOR_WEIGHT = 5.0
_RECENCY_HALF_LIFE_DAYS = 180.0
_TAG_PRIOR_WEIGHT = 2.0
_PREFERENCE_MARGIN = 0.3
```

增加可测试的 `as_of: datetime | None = None` 参数，并计算：

```python
weight = 0.5 ** (age_days / _RECENCY_HALF_LIFE_DAYS)
baseline = (weighted_scores + 5 * 7.0) / (weighted_count + 5)
```

- [ ] **步骤 3：实现平滑标签统计和分类**

标签保留 `count >= 2` 门槛；对每个标签计算原始平均分、加权计数、平滑分数、中心化差值和 0～100 偏好指数。按 `±0.3` 产生 `favorite_tags`、`avoid_tags`，并按偏好指数排序。

保留旧 `taste_dictionary` 的 `[count, raw_avg_score]` 格式和旧图表字段；在 `llm_summary` 增加 `rating_baseline`、`favorite_tags`、`avoid_tags`、`tag_preferences`。

- [ ] **步骤 4：运行画像测试确认通过**

运行：

```text
uv run pytest tests/services/test_user_profile_service.py -q
```

预期：新增画像测试全部 PASS，且无异常退出。

- [ ] **步骤 5：提交画像实现**

```text
git add backend/app/services/user_profile_service.py backend/tests/services/test_user_profile_service.py
git commit -m "feat: center and smooth user profile preferences"
```

### 任务 3：让推荐使用喜欢/回避标签

**文件：**
- 修改：`backend/app/agents/recommendation_agent.py:128-159`
- 修改：`backend/app/capabilities/anime.py:27-43`
- 修改：`backend/tests/agents/test_recommendation_agent.py`

- [ ] **步骤 1：编写失败测试**

扩展 `StubAnimeCapability` 记录调用参数，并添加：

```python
async def test_candidate_search_uses_favorite_tags_and_filters_avoid_tags():
    profile = profile_with_preferences(
        favorite_tags=["科幻"],
        avoid_tags=["校园"],
        watched_ids=[1],
    )
    anime = StubAnimeCapability(results=[
        {"id": 1, "name": "已看", "tags": ["科幻"]},
        {"id": 2, "name": "雷区作品", "tags": ["科幻", "校园"]},
        {"id": 3, "name": "合适作品", "tags": ["科幻"]},
    ])
    result = await RecommendationAgent(StubCapability(profile=profile), anime_capability=anime).execute(task)
    assert [item["id"] for item in result["candidates"]] == [3]
    assert anime.last_kwargs["tags"] == ["科幻"]


async def test_candidates_without_tags_are_not_dropped():
    result = await agent_with_profile(favorite_tags=["科幻"], avoid_tags=["校园"], results=[{"id": 2, "name": "未知标签"}])
    assert result["candidates"] == [{"id": 2, "name": "未知标签"}]
```

- [ ] **步骤 2：运行测试确认正确失败**

运行：

```text
uv run pytest tests/agents/test_recommendation_agent.py -q
```

预期：新增测试 FAIL，当前 agent 仍从 `taste_dictionary` 取标签，且不会过滤候选标签。

- [ ] **步骤 3：实现候选标签透传和过滤**

在 `AnimeCapability` 的搜索结果简化结构中透传标准化 `tags`。在 `RecommendationAgent._select_candidates` 中：

1. 优先使用 `profile.llm_summary.favorite_tags`；
2. 没有新字段时兼容回退到旧 `taste_dictionary`；
3. 用前 3 个喜欢标签搜索；
4. 排除 `watched_ids`；
5. 只有候选明确提供标签时才过滤与 `avoid_tags` 的交集；
6. 保持最多 20 个候选和现有搜索失败 fallback。

- [ ] **步骤 4：运行推荐测试确认通过**

运行：

```text
uv run pytest tests/agents/test_recommendation_agent.py tests/capabilities/test_recommendation.py -q
```

预期：全部 PASS。

- [ ] **步骤 5：提交推荐实现**

```text
git add backend/app/agents/recommendation_agent.py backend/app/capabilities/anime.py backend/tests/agents/test_recommendation_agent.py
git commit -m "feat: use preference tags for recommendation candidates"
```

### 任务 4：完整验证和收尾

**文件：**
- 检查：`backend/app/services/user_profile_service.py`
- 检查：`backend/app/agents/recommendation_agent.py`
- 检查：`backend/app/capabilities/anime.py`
- 检查：相关测试文件

- [ ] **步骤 1：运行完整相关测试**

运行：

```text
uv run pytest tests/services tests/capabilities tests/agents -q
```

预期：全部通过；允许已有 Pydantic 弃用警告，但不得出现新增失败或 traceback。

- [ ] **步骤 2：运行 lint**

运行：

```text
uv run ruff check app/services/user_profile_service.py app/capabilities/anime.py app/agents/recommendation_agent.py tests/services/test_user_profile_service.py tests/agents/test_recommendation_agent.py
```

预期：退出码 0。

- [ ] **步骤 3：检查 diff 和 worktree**

运行：

```text
git diff --check
git status --short
```

预期：无空白错误；只包含本计划涉及的文件。
