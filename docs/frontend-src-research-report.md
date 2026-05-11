# OtakuNeko Frontend `src/` 调研总结报告

> **调研日期**: 2026-05-09  
> **调研范围**: `e:\HACCI\Documents\tools\OtakuNeko\frontend\src\`  
> **关联后端**: `e:\HACCI\Documents\tools\OtakuNeko\backend\`

---

## 1. 技术栈概览

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | Next.js (App Router) | 16.1.6 |
| UI 库 | React | 19.2.3 |
| 组件库 | @lobehub/ui + antd | 4.35 / 6.3 |
| 样式 | Tailwind CSS + antd-style | 4.1 |
| 状态管理 | Zustand | 5.0 |
| 拖拽 | @dnd-kit | 6.3 |
| HTTP | fetch 原生 / axios | — / 1.13 |
| 构建 | Turbopack + React Compiler | — |
| 包管理 | pnpm | — |

---

## 2. 目录结构与模块划分

```
src/
├── app/                    # Next.js App Router 页面
│   ├── page.tsx            # 首页 → ChatPage (聊天)
│   ├── layout.tsx          # 根布局：LobeProvider + APPLayout
│   ├── APPLayout.tsx       # 全屏布局容器 (fixed 定位 + Sidebar)
│   ├── globals.css         # Tailwind + CSS 变量主题 (default/ocean/sakura)
│   ├── collections/page.tsx # 收藏管理页
│   ├── Timetable/page.tsx  # 排班表页 (拖拽 + 日历)
│   ├── Personal/page.tsx   # AI 角色工厂页
│   └── api/                # Next API Routes (代理层)
│       ├── collections/route.ts   # 收藏 API 代理
│       └── proxy-image/route.ts   # 豆瓣图片反防盗链代理
│
├── components/             # 业务 UI 组件 (6 个子模块)
│   ├── chat/               # 聊天界面 (ChatPage, ChatInput, ModelSelector, RoleSelector, SearchBar)
│   ├── collection/         # 收藏展示 (CollectionContent, MediaCard, BilibiliIcon)
│   ├── header/             # 各页面 Header (Chat/Collection/Timetable/Persona + User + SearchBar)
│   ├── timetable/          # 排班表拖拽系统 (TimelineBoard, DraggablePanel, DroppableCell 等 7 文件)
│   ├── Modal/              # 8 个全局弹窗 + SubjectForm 子表单 + types.ts
│   ├── providers/          # LobeProvider (主题上下文) + ColorSchemes
│   └── sidebar/            # RoleSidebar (角色侧栏)
│
├── features/               # 功能模块
│   ├── Sidebar/index.tsx   # 主导航侧栏 (DesktopSidebar)
│   └── Theme/              # 主题切换器 (ThemeSwitcher + ThemeModeSwitcher)
│
├── services/               # API 服务层 (9 文件)
│   ├── client.ts           # 通用 request<T>() 封装
│   ├── auth.ts             # 登录/用户
│   ├── collections.ts      # 收藏 CRUD
│   ├── scheduleService.ts  # 排班 + 收藏搜索回退
│   ├── bangumiService.ts   # Bangumi 日历 + 核心类型定义
│   ├── CalendarService.ts  # 日历 CSV/iCal 生成
│   ├── rss.ts              # RSS 订阅管理
│   ├── dashboard.ts        # 仪表板统计
│   └── search.ts           # 条目搜索 (原生 fetch，未用 client.ts)
│
├── lib/                    # 工具库
│   ├── fetcher.ts          # SSE 流式聊天 (chatWithBackend)
│   └── utils.ts            # cn() 类名合并
│
├── store/                  # Zustand 应用级 Store
│   ├── useApiStore.ts      # 15+ LLM 服务商 API Key 管理
│   ├── useRoleStore.ts     # 自定义 AI 角色 CRUD
│   ├── models.ts           # 类型定义 + MODEL_LIST
│   ├── presetRoles.ts      # 3 个预设 AI 角色
│   └── useHasHydrated.ts   # SSR 水合 Hook
│
└── stores/                 # Zustand 聊天 Store (历史遗留目录)
    └── useChatStore.ts     # 多会话聊天管理 (sessions + chatMessages Map)
```

---

## 3. 页面路由与功能矩阵

| 路由 | 页面 | 功能 | 核心依赖 |
|------|------|------|----------|
| `/` | 聊天 | AI 多轮对话、多模型切换、角色扮演、Tool Call 可视化 | `useChatStore`, `fetcher.ts`, `@lobehub/ui/chat` |
| `/collections` | 收藏 | 网格/列表视图、类型筛选、状态筛选、排序、搜索 | `collectionService`, `MediaCard` |
| `/Timetable` | 排班 | 拖拽排班、新番时间网格、标准通道视图、导出日历/TickTick | `@dnd-kit`, `TimelineBoard`, `DraggablePanel` |
| `/Personal` | 角色 | AI 角色创建/编辑、Emoji 头像、Prompt 配置、导出/导入 | `useRoleStore`, `RoleSidebar` |

---

## 4. 数据流架构

```
┌─────────────────────────────────────────────────┐
│                    UI Layer                       │
│  ChatPage / CollectionPage / TimetablePage / ... │
└──────────┬──────────────────────────────────────┘
           │ 调用
┌──────────▼──────────────────────────────────────┐
│              services/  (API 服务层)              │
│  client.ts → request<T>() 统一封装                │
│  auth.ts / collections.ts / scheduleService.ts   │
└──────────┬──────────────────────────────────────┘
           │ HTTP (localhost:8000/api/v1)
┌──────────▼──────────────────────────────────────┐
│           app/api/  (Next API Routes 代理)        │
│  /collections → 透传后端   /proxy-image → 反盗链  │
└──────────┬──────────────────────────────────────┘
           │ 或直连
┌──────────▼──────────────────────────────────────┐
│            Python FastAPI Backend                 │
│  /api/v1/chat, /collections, /schedules, ...     │
└─────────────────────────────────────────────────┘

状态管理 (Zustand):
  useChatStore ←→ ChatPage (消息/会话)
  useApiStore  ←→ ApiKeyModal (API Key), fetcher.ts (getState 读取)
  useRoleStore ←→ Personal (角色 CRUD), ChatPage (角色列表)
```

### 两条 HTTP 通道

1. **通用 API 通道**: `services/client.ts` → `request<T>()` → `fetch('http://localhost:8000/api/v1/...')`  
   JWT Token 自动注入，统一错误处理。用于收藏、排班、登录等。

2. **SSE 流式聊天通道**: `lib/fetcher.ts` → `chatWithBackend()` → `fetch('http://localhost:8000/api/v1/chat')`  
   自建 SSE 解析器，透传 API Key + Provider Endpoint。不走 `client.ts`。

3. **Next.js Rewrite 代理** (生产环境): `next.config.ts` → `API_PROXY_URL` 环境变量 → `/api/:path*` → 后端  
   开发时直连 localhost:8000，Docker 部署时通过 rewrite 代理到内部 backend 服务。

---

## 5. 问题诊断

### 5.1 严重问题 (Critical)

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | **FRONTEND_DOCUMENTATION.md 严重过期** — 文档描述了大量不存在的文件（`components/dashboard/`、`components/ui/`、`contexts/`、`hooks/` 等），与当前代码完全脱节 | [FRONTEND_DOCUMENTATION.md](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/FRONTEND_DOCUMENTATION.md) | 新人误导、AI Agent 误判代码结构 |
| 2 | **`useChatStore` 的 `chatMessages: Map` 持久化问题** — Zustand persist 中间件对 Map 类型序列化/反序列化不可靠，代码中多处加了 `typeof ...get === 'function'` 防御检查 | [useChatStore.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/stores/useChatStore.ts) | 潜在数据丢失、维护负担 |
| 3 | **`services/search.ts` 未复用 `client.ts`** — 直接用 `fetch` 而非 `request<T>()`，Token 注入和错误处理不一致 | [search.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/services/search.ts) | 代码风格分裂、Token 管理风险 |

### 5.2 中等问题 (Moderate)

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 4 | **`store/` vs `stores/` 目录分裂** — 无明确划分标准，`useChatStore.ts` 孤零零放在 `stores/` | 两个目录 | 合并到 `store/` |
| 5 | **硬编码的 API 地址** — `client.ts` 和 `fetcher.ts` 都硬编码 `localhost:8000`，生产环境依赖 Next.js rewrite | [client.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/services/client.ts) + [fetcher.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/lib/fetcher.ts) | 统一为环境变量 |
| 6 | **APPLayout 大量 inline styles** — 应迁移至 Tailwind 或 CSS Modules | [APPLayout.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/APPLayout.tsx) | 可维护性差 |
| 7 | **`scheduleService.ts` 职责越界** — API 层包含业务逻辑（空结果回退到 subjects 接口） | [scheduleService.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/services/scheduleService.ts#L28-L70) | 抽取到 hook 或 utils |
| 8 | **类型定义分散** — `BangumiItem`, `SubjectInfo` 等核心类型在 `bangumiService.ts`，但 `CollectionItem` 在 `collections.ts`，CalendarService、scheduleService 都依赖前者 | 多个文件 | 建立统一 `src/types/` 目录 |

### 5.3 轻微问题 (Minor)

| # | 问题 | 位置 |
|---|------|------|
| 9 | `globals.css` 定义了三套 CSS 变量主题（default/ocean/sakura），但有独立的 `ColorSchemes.ts` 和 LobeProvider 主题系统，两套主题体系并存 | [globals.css](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/globals.css) + [ColorSchemes.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/providers/ColorSchemes.ts) |
| 10 | 前端无任何测试文件（单元/集成/E2E），后端有完整的 `tests/` 目录 | — |
| 11 | `MODEL_LIST` 中模型 ID 为旧版（如 `gpt-3.5-turbo`, `claude-3-opus-20240229`），部分已退役 | [models.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/models.ts) |

---

## 6. 架构评估

### 优点

- **清晰的分层**: services → components → pages，职责边界明确
- **Next.js App Router**: 充分利用 RSC、Server Actions、API Routes 代理
- **Zustand 轻量状态管理**: 比 Redux 更适合此规模项目
- **@lobehub/ui 组件库**: 提供了 ChatItem、SideNav、DraggablePanel 等高质量 AI Chat 专用组件
- **类型安全**: 全 TypeScript + strict mode
- **Docker 就绪**: `output: "standalone"` + `API_PROXY_URL` 环境变量

### 改进空间

1. **文档与代码同步机制缺失** — 现有 `FRONTEND_DOCUMENTATION.md` 是早期版本的遗留产物
2. **目录组织** — `store/` vs `stores/` 需要统一
3. **测试覆盖** — 零测试，建议至少覆盖核心 service 层
4. **类型集中管理** — 建议建立 `src/types/` 避免循环依赖风险

---

## 7. 新创建的模块文档

本次调研补全了以下缺失的局部文档：

| 文档 | 路径 |
|------|------|
| Components 模块说明 | [frontend/src/components/README.md](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/README.md) |
| Services 模块说明 | [frontend/src/services/README.md](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/services/README.md) |
| Store 模块说明 | [frontend/src/store/README.md](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/README.md) |
| Lib 模块说明 | [frontend/src/lib/README.md](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/lib/README.md) |

---

## 8. 建议下一步行动

| 优先级 | 行动 | 预期收益 |
|--------|------|----------|
| P0 | 重写 `FRONTEND_DOCUMENTATION.md`，与当前代码同步 | 消除误导 |
| P1 | 合并 `stores/useChatStore.ts` → `store/` | 统一目录 |
| P1 | `useChatStore` 将 `chatMessages` 从 `Map` 改为 `Record<string, Message[]>` | 修复持久化可靠性 |
| P2 | 统一 `search.ts` 使用 `client.ts` 的 `request<T>()` | 代码一致性 |
| P2 | API 地址改为环境变量 `NEXT_PUBLIC_API_URL` | 部署灵活性 |
| P3 | 建立 `src/types/` 集中类型定义 | 可维护性 |
| P3 | 添加 service 层单元测试 | 质量保障 |
