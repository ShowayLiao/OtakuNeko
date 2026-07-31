# 个性化用户画像算法优化设计

## 目标

在保持现有画像输出兼容性的前提下，让推荐结果更贴近用户真实喜好：识别用户相对偏好的标签、回避标签、近期兴趣，并降低小样本和评分习惯差异带来的误判。

## 现状与范围

核心实现位于 `backend/app/services/user_profile_service.py`，推荐 agent 位于 `backend/app/agents/recommendation_agent.py`。

本次只改进：

- 评分中心化；
- 时间衰减；
- 小样本贝叶斯平滑；
- 喜欢/回避标签输出；
- 推荐候选选择和回避标签过滤。

不引入 embedding、LLM 画像调用或新的数据库表。

## 算法设计

### 1. 评分基准

评分基准使用用户个人评分习惯，并向固定中性先验收缩：

```text
recency_weight_i = 0.5 ** (age_days_i / 180)

baseline =
    (sum(recency_weight_i * score_i) + 5 * 7.0)
    / (sum(recency_weight_i) + 5)
```

- 中性先验为 `7.0`；
- 先验有效样本数为 `5`；
- 所有有效评分都参与基准计算，即使作品没有标签；
- 缺少 `updated_at` 的记录使用权重 `1.0`；
- 时间戳统一按 UTC 计算，半衰期为 180 天；
- 画像函数增加可选的 `as_of` 时间参数，生产默认当前 UTC，测试使用固定时间。

这样可以避免新用户单次评分直接决定画像，也能适应高分用户和低分用户不同的评分尺度。

### 2. 标签统计与平滑

标签仍至少出现 2 次才进入画像，保留旧的原始统计字段：

```text
raw_avg_score = total_score / count
```

用于偏好判断的标签分数使用标签级平滑：

```text
smoothed_score =
    (weighted_tag_score + 2 * baseline)
    / (weighted_tag_count + 2)
```

标签的中心化偏好为：

```text
preference_delta = smoothed_score - baseline
```

偏好指数映射为 0～100，基准分对应 50：

```text
preference_score = clamp(50 + preference_delta * 16.67, 0, 100)
```

标签分类采用中性区，避免微小评分差异造成误判：

- `preference_delta >= 0.3`：喜欢标签；
- `preference_delta <= -0.3`：回避标签；
- 其余：中性标签。

喜欢标签按 `preference_score` 降序排列，回避标签按 `preference_score` 升序排列。

### 3. 输出兼容性

保留现有字段：

- `llm_summary.total_rated`；
- `llm_summary.taste_dictionary`；
- `chart_data.radar`；
- `chart_data.bar_count`；
- `chart_data.bar_score`；
- `watched_ids`。

在 `llm_summary` 中新增：

```json
{
  "rating_baseline": 7.5,
  "favorite_tags": ["科幻", "冒险"],
  "avoid_tags": ["校园"],
  "tag_preferences": {
    "科幻": {
      "count": 4,
      "avg_score": 8.3,
      "smoothed_score": 8.0,
      "preference_score": 76,
      "preference_delta": 0.5,
      "weighted_count": 3.2
    }
  }
}
```

原始 `taste_dictionary` 继续按出现次数排序，供旧调用方兼容；新的推荐路径使用 `favorite_tags`，不再默认取出现次数最高的标签。

### 4. 推荐候选选择

`RecommendationAgent` 调整为：

1. 优先读取 `favorite_tags`，按偏好指数排序；
2. 使用前 3 个喜欢标签作为搜索标签；
3. 排除已观看作品；
4. 如果搜索结果携带标签，则过滤与 `avoid_tags` 相交的作品；
5. 缺少候选标签数据时保留候选，避免因上游数据不完整导致结果为空；
6. 如果没有喜欢标签，保留现有冷启动回复。

搜索结果保留并透传标准化的 `tags` 字段，以支持第 4 步。

## 错误处理

- 空收藏、无有效评分、无有效标签仍返回结构化空画像；
- 单条记录格式错误继续跳过，不影响其他记录；
- 无法解析时间戳的记录使用权重 `1.0`；
- 评分基准和偏好指数限制在合法范围内；
- 候选搜索失败继续返回现有诚实 fallback。

## 测试设计

新增画像服务测试，覆盖：

- 固定 `as_of` 下的时间衰减；
- 新用户评分向 `7.0` 先验收缩；
- 高于/低于个人基准的标签分别进入喜欢/回避集合；
- `±0.3` 中性区不产生误判；
- 标签小样本平滑；
- 无标签评分仍参与基准计算；
- 旧字段保持存在且格式不变。

新增或扩展推荐 agent 测试，覆盖：

- 使用喜欢标签而不是频次第一标签进行搜索；
- 过滤回避标签和已观看作品；
- 候选没有标签时不被误删；
- 冷启动和搜索失败行为保持不变。

验证命令：

```text
uv run pytest tests/services/test_user_profile_service.py tests/capabilities/test_recommendation.py tests/agents/test_recommendation_agent.py -q
uv run ruff check app/services/user_profile_service.py app/capabilities/anime.py app/agents/recommendation_agent.py tests/services/test_user_profile_service.py tests/agents/test_recommendation_agent.py
```
