# 收藏全量统计能力实现计划

## 目标

新增数据库聚合的只读 `get_collection_statistics` 能力，返回指定条目类型的收藏总数、五种观看状态数量和基于作品标签的前三个题材标签；用户身份由 Runtime 注入，模型不能传入 `user_id`。

## 修改范围

- `backend/app/schemas/dashboard.py`：增加版本稳定的统计输出模型。
- `backend/app/services/stats_service.py`：增加用户范围的状态聚合和标签聚合查询。
- `backend/app/capabilities/stats.py`：注册并执行 `get_collection_statistics`。
- `backend/app/api/v1/dashboard.py`：暴露对应的认证只读 HTTP 接口。
- `backend/tests/capabilities/test_stats.py`：验证能力元数据、可信身份和结果包装。
- `backend/tests/services/test_stats_service.py`：验证状态、标签去重、用户隔离和条目类型过滤。

## 行为约束

- `list_collections` 仍是有界列表，不能用于全量统计。
- 统计动作只读取当前认证用户的数据，不接受模型提供的 `user_id`。
- 状态始终返回五个固定键，缺失状态为 `0`。
- 题材统计按每部作品去重标签；当前数据库没有独立 Genre 表，因此结果明确标为作品标签聚合。
- 完整性由数据库查询结果决定；标签覆盖率单独返回，不能把缺失标签伪装成完整题材数据。

## 验证

```powershell
uv run --directory backend pytest tests/capabilities/test_stats.py tests/services/test_stats_service.py -q
uv run --directory backend ruff check app tests
```
