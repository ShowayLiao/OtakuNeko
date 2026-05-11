# Agents 模块 — AI 智能代理层

## 模块简介

基于 LangGraph 构建的 ReAct（Reasoning + Acting）智能代理工作流引擎。
通过将业务能力封装为 Tool，让大语言模型自主决策调用哪个工具完成任务，
实现自然语言驱动的动画搜索、分析、推荐与用户画像生成。

## 核心功能

| 功能 | 实现方式 |
|------|----------|
| 动画详情查询 | `get_anime_info` — 通过 Bangumi ID 获取完整条目信息 |
| 观众口碑分析 | `fetch_audience_reviews` — 获取 Bangumi 短评/长评 |
| 制作团队分析 | `get_anime_staff` — 获取导演/编剧/制作公司 |
| 声优阵容分析 | `get_anime_cast` — 获取核心角色配音演员 |
| 高级动画搜索 | `search_anime_advanced` — 支持关键词+标签+评分+日期多条件搜索 |
| 当前时间查询 | `get_current_time` — 返回日期/时间/星期等本地时间 |
| 用户画像生成 | `generate_user_profile_tool` — 基于频次+平均分算法生成用户画像 |

## 文件结构说明

```
agents/
├── __init__.py         # 包入口（待实现）
├── graph.py            # LangGraph 工作流引擎（ReAct 循环 + SSE 事件流）
├── tools.py            # 7 个 LangChain Tool 定义（Tool 封装 + 参数翻译）
└── nodes/
    ├── __init__.py      # nodes 包入口（待实现）
    └── basic_node.py    # 基础节点模板（待实现）
```

### graph.py — 工作流引擎 ([源码](graph.py))

- **类 `ChatWorkflow`**：封装整个 ReAct 循环
  - 接收前端传来的 API key / base_url / model / messages / temperature
  - 初始化 `ChatOpenAI` 模型，绑定 7 个工具
  - 构建 LangGraph 图：`START → agent → [tools_condition] → tools → agent → END`
  - 通过 `astream_events` 流式输出三种事件：
    - `message_chunk` — 打字机效果的文本
    - `tool_start` — 工具调用开始（含参数）
    - `tool_end` — 工具调用结束（含结果）

### tools.py — 工具集 ([源码](tools.py))

每个工具使用 `@tool` 装饰器定义，包含完整的 docstring、参数说明和使用示例。
所有工具均为 async 函数，支持错误安全返回（不会因异常而中断对话）。

**依赖关系**：
- 调用 `app.services.bangumi_service`（动画数据）
- 调用 `app.services.bangumi_client`（Bangumi API 搜索）
- 调用 `app.services.user_profile_service`（用户画像算法）
- 调用 `app.schemas.bangumi`（SubjectDetail 类型）

## 依赖关系

```
            ┌────────────────┐
            │  agent.py      │  ← FastAPI SSE endpoint (/api/v1/agent/chat)
            │  (api/v1)      │
            └───────┬────────┘
                    │ 调用
            ┌───────▼────────┐
            │   graph.py     │  ← ChatWorkflow.stream_chat()
            └───────┬────────┘
                    │ 绑定 & 执行
            ┌───────▼────────┐
            │   tools.py     │  ← 7 个 @tool 函数
            └───────┬────────┘
                    │ 调用
        ┌───────────┼───────────┐
        ▼           ▼           ▼
  services/    services/   services/
  bangumi_*    bangumi_    user_profile_
               client      service
```

**被谁调用**：
- `app/api/v1/agent.py` → `ChatWorkflow.stream_chat()`

**调用谁**：
- `app.services.bangumi_service` — `fetch_subject_by_id`, `get_audience_feedback`, `get_staff_info`, `get_cast_info`
- `app.services.bangumi_client` — `search_subjects_advanced`
- `app.services.user_profile_service` — `generate_user_profile`

## 设计模式

本模块采用 **ReAct (Reasoning + Acting)** 模式：

1. 用户发消息 → Agent 节点（LLM 推理）
2. LLM 决定是否调用工具 → 若需要，输出 tool_call
3. 工具执行 → 结果返回给 LLM
4. LLM 基于工具结果继续推理 → 生成最终回复

图结构（LangGraph StateGraph）：
```
START → agent ──[工具调用?]──→ tools → agent → END
                └─[无需工具]─→ END
```

## 当前状态与待办

| 项目 | 状态 |
|------|------|
| 7 个工具定义 | ✅ 完成 |
| ReAct 工作流 | ✅ 完成 |
| SSE 流式事件 | ✅ 完成 |
| ToolMessage 序列化 | ✅ 完成 |
| `__init__.py` 包入口 | ❌ 空 TODO |
| `nodes/basic_node.py` 自定义节点 | ❌ 空 TODO |
| `nodes/__init__.py` | ❌ 空 TODO |
| 用户画像工具数据自动获取 | ❌ 需手动传入收藏数据（缺口） |
