# Agents 模块 — AI 智能代理层

## 模块简介

基于 LangGraph 构建的 **Think-Speak 双节点** 智能代理工作流引擎。
将推理（think）与回复（speak）物理分离为两个独立节点，
通过 `astream_events` v2 的 `metadata.langgraph_node` 原生流式分流，
彻底告别脆弱的 `<think>` 标签解析。

业务能力封装为 Tool，大语言模型在 think 节点自主决策调用工具完成任务，
推理完毕后路由到 speak 节点生成面向用户的自然语言回复。

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
├── __init__.py            # 包入口
├── graph.py               # LangGraph 工作流引擎（Think-Speak 双节点 + SSE 事件流）
├── registry.py            # ToolRegistry — 统一工具注册/发现中心 (M2b)
├── tools.py               # 兼容转发 → tools/ 子包
├── tools/
│   ├── __init__.py         # ALL_TOOLS 列表
│   ├── base.py             # ToolResult schema + log_tool_call 装饰器 (M2b)
│   ├── anime.py            # get_anime_info / fetch_audience_reviews / get_anime_staff / get_anime_cast
│   ├── search.py           # search_anime_advanced（已重构拆分）
│   ├── datetime.py         # get_current_time
│   └── profile.py          # generate_user_profile_tool
└── nodes/
    ├── __init__.py          # nodes 包入口
    └── basic_node.py        # 基础节点模板
```

### graph.py — 工作流引擎 ([源码](graph.py))

- **类 `ChatWorkflow`**：封装 Think-Speak 双节点工作流
  - 接收前端传来的 API key / base_url / model / messages / temperature / db_path
  - 初始化 `ChatOpenAI` 模型，think 节点绑定工具，speak 节点不绑定
  - 构建 LangGraph 图：`START → think → [tools?] → tools → think` 循环，推理完毕路由 `speak → END`
  - 通过 `astream_events` v2 + `metadata.langgraph_node` 流式分流：
    - `node_name="think"` → `thinking_start/chunk/end` + `reasoning_trace`
    - `node_name="speak"` → `message_start/chunk/end`
    - `on_tool_start/end` → `tool_call_start/end` + `progress`
- **`CodingAgentState`**（六字段状态）：
  - `messages`、`reasoning_trace`、`current_dir`、`plan`、`completed_steps`、`last_terminal_output`
- **`THINK_SYSTEM_PROMPT`**：内部推理引擎 — 分析意图 → 搜索数据 → 整合信息
- **`SPEAK_SYSTEM_PROMPT`**：面向用户助手 — 基于推理结果自然回复（不可调用工具）
- **工具系统**（M2b）：`ToolRegistry` 统一注册，`ToolNode` 和 `bind_tools` 动态从 `registry.get_all()` 拉取
- **持久化**：`AsyncSqliteSaver` + LangGraph InMemoryStore 长记忆
- **思考中断**（可选）：`interrupt_before=["speak"]` + `POST /chat/resume` 审核端点

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
            │  (api/v1)      │     /chat/reasoning/{id} / /chat/resume
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

本模块采用 **Think-Speak 双节点分离** 模式：

1. 用户发消息 → think 节点（LLM 推理 + 工具调用）
2. LLM 决定是否调用工具 → 若需要，输出 tool_call → tools 执行 → 返回 think
3. 推理完毕（无工具调用）→ 路由到 speak 节点
4. speak 节点基于全部推理结果 → 生成用户可读的自然语言回复

图结构（LangGraph StateGraph）：
```
START → think ──[工具调用?]──→ tools → think (循环)
                 └─[推理完毕]──→ speak → END

可选：interrupt_before=["speak"] → 人工审核推理后再继续
```

### 节点职责

| 节点 | LLM 配置 | System Prompt | SSE 事件 |
|------|---------|---------------|----------|
| `think` | `llm.bind_tools(tools)` | 内部推理引擎，可用工具 | `thinking_start/chunk/end` + `reasoning_trace` |
| `speak` | `llm`（无工具绑定） | 面向用户回复，不可用工具 | `message_start/chunk/end` |
| `tools` | ToolNode | — | `tool_call_start/end` + `progress` |

### SSE 事件类型

| 事件 | 触发时机 | 方向 |
|------|---------|------|
| `thinking_start/chunk/end` | think 节点流式推理 | 前端 → 折叠面板 |
| `reasoning_trace` | think 节点完成（一次性推送完整推理） | 前端 → "查看推理过程" 面板 |
| `tool_call_delta/start/end` | 工具调用过程 | 前端 → 状态指示 |
| `progress` | 工具调用完成 | 前端 → 进度更新 |
| `message_start/chunk/end` | speak 节点流式回复 | 前端 → 打字机直出 |
| `interrupt` | think→speak 被 `interrupt_before` 暂停 | 前端 → 审核交互 |
| `error` | 执行异常 | 前端 → 错误提示 |

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat` | POST | 用户发消息 → 流式 SSE 返回 |
| `/api/v1/chat/history` | GET | 获取对话历史消息 |
| `/api/v1/chat/reasoning/{thread_id}` | GET | 获取最新推理过程文本 |
| `/api/v1/chat/resume` | POST | 恢复 interrupt 暂停的对话（decision=approve/reject） |
| `/api/v1/chat/history/{thread_id}` | DELETE | 删除对话线程 |
| `/api/v1/chat/threads` | GET | 列出所有对话线程 |

## 当前状态与待办

| 项目 | 状态 |
|------|------|
| 7 个工具定义 | ✅ 完成 |
| Think-Speak 双节点工作流 | ✅ 完成 |
| SSE 流式事件（含 reasoning_trace） | ✅ 完成 |
| ToolMessage 序列化 | ✅ 完成 |
| AsyncSqliteSaver checkpoint 持久化 | ✅ 完成 |
| CodingAgentState 六字段状态 | ✅ 完成 |
| LongTermMemory → LangGraph Store 迁入 | ✅ 完成 |
| DELETE /chat/history API | ✅ 完成 |
| ToolRegistry 统一注册中心 | ✅ 完成 |
| tools/ 目录拆分 + ToolResult schema + 日志 | ✅ 完成 |
| GET /chat/reasoning/{id} API | ✅ 完成 |
| POST /chat/resume (interrupt 恢复) | ✅ 完成 |
| `interrupt_before=["speak"]` 思考中断 | ✅ 完成 |
| `reasoning_trace` SSE 持久化推送 | ✅ 完成 |
| `__init__.py` 包入口 | ❌ 空 TODO |
| `nodes/basic_node.py` 自定义节点 | ❌ 空 TODO |
| `nodes/__init__.py` | ❌ 空 TODO |
| 用户画像工具数据自动获取 | ❌ 需手动传入收藏数据（缺口） |
| MCP 协议接入预留 | 🔧 [计划中](../../docs/plans/tool-registry-mcp-integration.md) |
