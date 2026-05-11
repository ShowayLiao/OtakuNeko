# Worker 模块 — 异步任务队列

## 模块简介

异步后台任务队列层。计划基于 Celery 实现定时/异步任务，目前处于**未实现**状态（所有文件仅含 TODO 占位）。

## 当前状态

| 文件 | 状态 |
|------|------|
| `__init__.py` | ❌ TODO 占位 — 无实际代码 |
| `celery_app.py` | ❌ TODO 占位 — 无 Celery 实例配置 |

## 计划用途

1. 定时同步 Bangumi 数据（用户收藏、日历信息）
2. 定时同步 bangumi-data 番剧放送元数据
3. 批量数据导入/清洗（豆瓣 → Bangumi 格式转换）
4. RSS 定时抓取与规则匹配（qBittorrent 联动）
5. 用户画像批量生成

## 依赖关系

**被谁调用**：无（尚未集成到主流程）

**调用谁**：无（尚未实现）

## 后续待办

- [ ] 配置 Celery app 实例（broker: Redis/RabbitMQ）
- [ ] 实现 Celery Beat 定时调度
- [ ] 编写具体的 task 函数（调用 services）
- [ ] 集成到 `docker-compose.yml`（独立 worker 容器）
