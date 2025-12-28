# OtakuNeko 项目说明

## 项目概述

OtakuNeko 是一个基于 AI 的动漫收藏管理平台，支持从 Bangumi 和豆瓣等多个数据源同步用户的收藏数据，并提供智能化的数据管理和分析功能。

### 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **前端** | Next.js 16 + React 19 | 现代化的 React 框架，支持服务端渲染和静态生成 |
| **前端** | TypeScript | 类型安全的 JavaScript 超集 |
| **前端** | Tailwind CSS 4 | 原子化 CSS 框架，快速构建响应式界面 |
| **前端** | Zustand | 轻量级状态管理库 |
| **前端** | Axios | HTTP 客户端，用于与后端 API 通信 |
| **前端** | Lucide React | 图标库 |
| **前端** | Recharts | 数据可视化图表库 |
| **后端** | FastAPI | 高性能异步 Web 框架 |
| **后端** | SQLModel | 基于 Pydantic 和 SQLAlchemy 的 ORM |
| **后端** | PostgreSQL | 关系型数据库 |
| **后端** | Python 3.11+ | 后端开发语言 |
| **部署** | Docker + Docker Compose | 容器化部署方案 |

### 项目结构

```
OtakuNeko/
├── backend/                 # 后端项目
│   ├── app/
│   │   ├── api/            # API 路由层
│   │   ├── models/         # 数据模型
│   │   ├── services/       # 业务逻辑层
│   │   ├── core/           # 核心配置
│   │   └── agents/         # AI 智能代理（预留）
│   ├── tests/              # 测试代码
│   └── requirements.txt    # Python 依赖
├── frontend/               # 前端项目
│   ├── src/
│   │   ├── app/           # Next.js App Router 页面
│   │   ├── components/    # React 组件
│   │   ├── contexts/      # React Context 状态管理
│   │   ├── hooks/         # 自定义 Hooks
│   │   └── lib/           # 工具函数和 API 客户端
│   ├── public/            # 静态资源
│   └── package.json       # Node.js 依赖
├── docker-compose.yml     # Docker 编排配置
└── .env                  # 环境变量配置
```

## 1. 后端架构

### 1.1 模块功能索引

| 文件夹     | 主要角色与职责                                             | 核心文件示例                          |
|------------|----------------------------------------------------------|---------------------------------------|
| **core/**  | 项目核心配置与基础组件，提供全局共享的配置和工具函数       | `config.py` (环境变量配置)             |
| **api/**   | API接口层，负责处理HTTP请求和响应，采用版本化路由管理      | `v1/collections.py` (收藏数据同步接口)  |
| **models/**| 数据模型层，定义数据库表结构和实体关系，支持多数据源       | `subject.py` (通用条目模型), `collection.py` (收藏模型) |
| **services/** | 业务逻辑层，封装核心业务流程和数据处理逻辑               | `bangumi_service.py` (Bangumi数据处理), `db_service.py` (豆瓣数据处理) |
| **agents/**| AI智能代理层，用于实现基于数据的AI应用功能                 | `graph.py` (AI工作流定义，待实现)      |

### 详细说明

- **core/**：存放项目的核心配置信息，如数据库连接字符串、API密钥等环境变量配置，是整个项目的基础支撑。
- **api/**：采用RESTful API设计，通过版本化路由（如v1）组织接口，将HTTP请求路由到相应的业务逻辑处理函数。
- **models/**：使用SQLModel定义数据库表结构，同时提供数据验证功能，支持多数据源（Bangumi、豆瓣等）的数据存储。
- **services/**：实现核心业务逻辑，如数据的CRUD操作、数据转换、业务规则验证等，是API层和数据层之间的桥梁。包含Bangumi和豆瓣的数据处理服务。
- **agents/**：为AI功能预留的模块，用于实现基于已有数据的智能应用，如推荐系统、数据分析等。

### 1.2 数据流向分析

当数据从外部进入系统时，数据流向如下：

```
外部数据源 (Bangumi/豆瓣) → API路由层 → 服务层 → 数据模型层 → 数据库
```

#### 详细流程

1. **API入口**：数据通过RESTful API接口进入系统
2. **数据验证**：API层验证请求参数和数据格式
3. **服务层处理**：调用相应的服务函数进行业务逻辑处理
4. **数据转换**：对于多数据源，进行ETL数据转换
5. **数据库操作**：将处理后的数据持久化到数据库
6. **响应返回**：将处理结果转换为JSON格式返回给客户端

## 2. 前端架构

### 2.1 技术选型

| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 16.1.0 | React 框架，提供 App Router、SSR、SSG 等功能 |
| React | 19.2.3 | UI 库，提供组件化开发能力 |
| TypeScript | 5.x | 类型系统，提供类型安全 |
| Tailwind CSS | 4.x | 原子化 CSS 框架，快速构建样式 |
| Zustand | 5.0.9 | 轻量级状态管理库，用于全局状态管理 |
| Axios | 1.13.2 | HTTP 客户端，用于 API 调用 |
| Lucide React | 0.562.0 | 图标库 |
| Recharts | 3.6.0 | 数据可视化图表库 |
| React Compiler | 1.0.0 | React 编译器优化 |

### 2.2 目录结构

```
frontend/
├── public/                 # 静态资源
│   ├── Icon.png           # 应用图标
│   └── *.svg              # SVG 图标文件
├── src/
│   ├── app/               # Next.js App Router 页面
│   │   ├── api/          # API 路由（Next.js API Routes）
│   │   │   └── collections/
│   │   │       └── route.ts
│   │   ├── collection/    # 单个收藏详情页
│   │   │   └── page.tsx
│   │   ├── collections/   # 收藏列表页
│   │   │   └── page.tsx
│   │   ├── layout.tsx     # 根布局
│   │   ├── page.tsx       # 首页
│   │   └── globals.css    # 全局样式
│   ├── components/        # React 组件
│   │   ├── chat/         # 聊天相关组件
│   │   │   ├── ChatInput.tsx
│   │   │   ├── EmptyState.tsx
│   │   │   ├── MessageAttachment.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── MessageSkeleton.tsx
│   │   │   └── ToolsPanel.tsx
│   │   ├── dashboard/    # 仪表盘组件
│   │   │   ├── AICoreStatus.tsx
│   │   │   ├── AnalysisInsights.tsx
│   │   │   ├── AnimationManager.tsx
│   │   │   ├── PluginManager.tsx
│   │   │   └── SyncCard.tsx
│   │   ├── layout/       # 布局组件
│   │   │   ├── Header.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── settings/     # 设置相关组件
│   │   │   └── SettingsModal.tsx
│   │   ├── ui/           # UI 基础组件
│   │   │   ├── Badge.tsx
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Checkbox.tsx
│   │   │   ├── Switch.tsx
│   │   │   ├── Toast.tsx
│   │   │   ├── Input.tsx
Dialog.tsx
│   │   │   └── ThemeSwitcher.tsx
│   │   ├── CollectionGridPage.tsx
│   │   ├── DoubanImportDialog.tsx
│   │   ├── ManualAddDialog.tsx
│   │   ├── NavPillSkeleton.tsx
│   │   ├── PosterCard.tsx
│   │   └── SortDropdown.tsx
│   ├── contexts/         # React Context 状态管理
│   │   ├── ChatContext.tsx
│   │   └── SettingsContext.tsx
│   ├── hooks/            # 自定义 Hooks
│   │   └── useSync.ts
│   └── lib/              # 工具函数和 API 客户端
│       ├── api.ts
│       ├── syncStore.ts
│       └── manualAddDialogStore.ts
├── .gitignore
├── package.json
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.mjs
└── next.config.ts
```

### 2.3 核心组件说明

#### 2.3.1 布局组件

**Sidebar (侧边栏)** - `src/components/layout/Sidebar.tsx`
- 提供应用主导航菜单
- 包含 Chat、Collections、Tools、Role、Settings 等导航项
- 使用 Lucide React 图标库
- 支持路由高亮显示

**Header (顶部栏)** - `src/components/layout/Header.tsx`
- 显示当前页面标题
- 提供用户操作入口
- 包含搜索框功能，支持搜索条目
- 显示用户头像或用户名首字母
- 显示收藏统计信息和同步按钮
- 支持一键同步功能

#### 2.3.2 页面组件

**Collections Page (收藏列表页)** - `src/app/collections/page.tsx`
- 显示用户的收藏列表
- 支持按类型筛选（书籍、动画、音乐、游戏、三次元）
- 支持按状态筛选（在看、已看完、想看、搁置、抛弃）
- 支持排序（更新时间、评分、排名、日期）
- 实现无限滚动加载
- 使用 `react-intersection-observer` 实现滚动检测

**Collection Page (收藏详情页)** - `src/app/collection/page.tsx`
- 显示单个收藏的详细信息
- 可能包含编辑功能

**Home Page (首页)** - `src/app/page.tsx`
- 应用首页，包含仪表盘概览
- 初始化数据加载

#### 2.3.3 UI 组件

**PosterCard (海报卡片)** - `src/components/PosterCard.tsx`
- 显示单个条目的海报和信息
- 包含封面、标题、评分、状态等信息
- 支持点击跳转到详情页

**SortDropdown (排序下拉菜单)** - `src/components/SortDropdown.tsx`
- 提供排序选项
- 支持多种排序方式

**ThemeSwitcher (主题切换器)** - `src/components/ThemeSwitcher.tsx`
- 支持亮色/暗色主题切换
- 使用 localStorage 保存主题偏好

**Checkbox (复选框)** - `src/components/ui/Checkbox.tsx`
- 可复用的复选框组件
- 支持自定义样式和回调函数
- 支持禁用状态
- 包含完整的无障碍支持（ARIA属性、键盘导航）
- 使用 Flexbox 布局确保图标居中
- 支持点击整个区域触发状态切换

**NavPillSkeleton (导航药丸骨架屏)** - `src/components/NavPillSkeleton.tsx`
- 用于加载状态的骨架屏组件
- 提供视觉反馈，改善用户体验

#### 2.3.4 聊天组件

**ChatInput (聊天输入框)** - `src/components/chat/ChatInput.tsx`
- 用户输入聊天消息
- 支持发送消息

**MessageBubble (消息气泡)** - `src/components/chat/MessageBubble.tsx`
- 显示聊天消息
- 区分用户消息和 AI 消息

**ToolsPanel (工具面板)** - `src/components/chat/ToolsPanel.tsx`
- 提供聊天相关的工具选项

#### 2.3.5 设置组件

**SettingsModal (设置模态框)** - `src/components/settings/SettingsModal.tsx`
- 提供全局设置界面
- 支持用户名配置
- 支持游客模式（Guest Mode）
- 支持自定义头像
- 支持 Bangumi 用户信息验证
- 游客模式下完全绕过 API 验证
- 实时更新预览用户信息
- 防止意外触发 API 调用

#### 2.3.6 对话框组件

**ManualAddDialog (手动添加对话框)** - `src/components/ManualAddDialog.tsx`
- 支持手动添加收藏条目
- 提供条目搜索功能
- 支持编辑已有收藏
- 使用全局用户名配置
- 防抖搜索优化性能

**DoubanImportDialog (豆瓣导入对话框)** - `src/components/DoubanImportDialog.tsx`
- 支持从豆瓣导入收藏数据
- 文件上传功能
- 使用全局用户名配置
- 显示导入进度和结果

#### 2.3.7 其他组件

**CollectionGridPage (收藏网格页面)** - `src/components/CollectionGridPage.tsx`
- 收藏列表的网格展示组件
- 支持筛选、排序、搜索
- 实现无限滚动加载

### 2.4 状态管理

#### 2.4.1 React Context

**ChatContext** - `src/contexts/ChatContext.tsx`
- 管理聊天相关的全局状态
- 提供聊天消息、发送状态等数据
- 使用 React Context API 实现

**SettingsContext** - `src/contexts/SettingsContext.tsx`
- 管理全局设置状态
- 提供用户名、游客模式、用户信息等配置
- 使用 localStorage 持久化设置
- 支持实时更新和响应式变化

#### 2.4.2 Zustand Store

**syncStore** - `src/lib/syncStore.ts`
- 管理数据同步相关的全局状态
- 使用 Zustand 实现轻量级状态管理
- 提供收藏数量统计、同步状态、同步错误等信息
- 支持按类型获取收藏数量
- 支持执行同步操作
- 所有同步操作都需要传入用户名参数

**manualAddDialogStore** - `src/lib/manualAddDialogStore.ts`
- 管理手动添加对话框的状态
- 控制对话框的打开/关闭
- 管理选中的条目信息

#### 2.4.3 自定义 Hooks

**useSync** - `src/hooks/useSync.ts`
- 封装数据同步逻辑
- 集成 syncStore 和 SettingsContext
- 提供同步功能、收藏数量统计等
- 自动使用全局用户名配置
- 提供错误处理和用户反馈

### 2.5 API 客户端

**api.ts** - `src/lib/api.ts`

使用 Axios 创建的 HTTP 客户端，封装了所有后端 API 调用：

```typescript
const api = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});
```

**主要 API 函数**：

| 函数名 | 功能 | 端点 |
|--------|------|------|
| `fetchDashboardStats()` | 获取仪表盘统计数据 | `GET /dashboard/stats` |
| `syncUser()` | 同步用户数据 | `POST /collections/sync` |
| `getUserCollectionCount()` | 获取用户收藏数量 | `GET /collections/count` |
| `searchSubjects()` | 搜索条目 | `GET /subjects` |
| `getUserCollections()` | 获取用户收藏列表 | `GET /collections` |
| `uploadDoubanFile()` | 上传豆瓣数据文件 | `POST /collections/sync/douban` |
| `fetchBangumiUser()` | 获取 Bangumi 用户信息 | `GET https://api.bgm.tv/v0/users/{username}` |
| `createManualCollection()` | 创建手动收藏 | `POST /collections/manual` |

**类型定义**：

```typescript
// Dashboard 统计数据
interface DashboardStats {
  total_subjects: number;
  total_collections: number;
  system_status: string;
  recent_activity: RecentActivityItem[];
}

// 条目数据
interface Subject {
  id: number;
  name: string;
  name_cn: string;
  type: number;
  cover_url: string;
  summary: string;
  date: string;
  platform?: string;
  eps?: number;
  volumes?: number;
  score?: number;
  rank?: number;
  collection_total?: number;
  tags: string[];
  meta_tags: string[];
  infobox: Record<string, string>;
  rating_details: Record<string, any>;
  images: Record<string, any>;
}

// 收藏数据
interface Collection {
  id: number;
  user_id: number;
  subject_id: number;
  status: number;
  rate: number;
  comment: string;
  tags: string[];
  updated_at: string;
  created_at: string;
}

// 收藏+条目数据
interface CollectionWithSubject {
  collection: Collection;
  subject: Subject;
}

// Bangumi 用户信息
interface BangumiUser {
  id: number;
  username: string;
  nickname: string;
  sign: string;
  avatar: {
    large: string;
    medium: string;
    small: string;
  };
}
```

### 2.6 Next.js 配置

**next.config.ts** - `next.config.ts`

```typescript
const nextConfig: NextConfig = {
  reactCompiler: true,  // 启用 React 编译器优化
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'picsum.photos',
      },
      {
        protocol: 'https',
        hostname: 'lain.bgm.tv',  // Bangumi 图片域名
      },
      {
        protocol: 'https',
        hostname: '**.doubanio.com',  // 豆瓣图片域名（支持所有子域名）
      },
    ],
  },
};
```

**关键配置说明**：
- `reactCompiler: true`：启用 React 编译器，自动优化组件性能
- `images.remotePatterns`：配置允许加载的外部图片域名
  - 支持 Bangumi 的图片域名 `lain.bgm.tv`
  - 支持豆瓣的所有子域名 `**.doubanio.com`（如 `img3.doubanio.com`）

### 2.7 样式系统

**Tailwind CSS 4** - 原子化 CSS 框架

- 使用 Tailwind CSS 4 的最新特性
- 支持深色模式（通过 `data-theme` 属性）
- 使用 `clsx` 和 `tailwind-merge` 进行样式合并

**全局样式** - `src/app/globals.css`
- 定义全局 CSS 变量
- 设置基础样式
- 支持主题切换

### 2.8 主题系统

实现亮色/暗色主题切换：

1. **防闪烁脚本**（在 `layout.tsx` 中）：
   - 在 React 加载前执行
   - 立即应用保存的主题
   - 避免页面闪烁

2. **主题切换组件**（`ThemeSwitcher.tsx`）：
   - 提供主题切换按钮
   - 使用 `localStorage` 保存主题偏好
   - 切换 `data-theme` 属性

### 2.9 性能优化

1. **React Compiler**：自动优化组件渲染
2. **无限滚动**：使用 `react-intersection-observer` 实现懒加载
3. **图片优化**：使用 Next.js Image 组件优化图片加载
4. **代码分割**：使用 Next.js 的动态导入功能
5. **防抖处理**：在搜索功能中使用防抖优化性能
6. **状态管理优化**：使用 Zustand 实现轻量级全局状态管理

### 2.10 开发命令

```bash
# 开发模式
npm run dev

# 构建生产版本
npm run build

# 启动生产服务器
npm run start

# 代码检查
npm run lint

# 类型检查
npm run typecheck
```

## 3. 数据流向分析

### 3.1 Bangumi 数据同步流程

当Bangumi的JSON数据发送到后端时，数据流向如下：

```
客户端 → API路由 (api/v1/collections.py) → 服务层 (services/bangumi_service.py) → 数据模型 (models/subject.py) → 数据库
```

#### 详细流程

1. **API入口**：数据通过`GET /api/v1/collections/sync/{username}`接口进入系统，由`backend/app/api/v1/collections.py`中的`sync_collections_endpoint`函数接收。

2. **数据获取**：API层调用`bangumi_client.py`中的`fetch_user_collections`函数从Bangumi API获取用户收藏数据。

3. **数据验证**：API层首先验证必要字段（id和name）是否存在，如果缺失则返回400错误。

4. **服务层处理**：验证通过后，调用`services/bangumi_service.py`中的`upsert_subject`函数处理数据。

5. **数据解析与转换**：服务层对原始Bangumi数据进行解析，提取并转换为适合数据库存储的格式：
   - 从`images`字段中提取封面图片URL
   - 将`tags`数组转换为仅包含name的列表
   - 从`rating`字段中提取评分信息

6. **数据库操作**：根据Bangumi ID查询数据库，决定执行插入或更新操作，最终将数据持久化到数据库。

7. **响应返回**：操作完成后，将处理结果转换为JSON格式返回给客户端。

### 3.2 豆瓣数据导入流程

当用户上传豆瓣JSON文件时，数据流向如下：

```
客户端上传文件 → API路由 (api/v1/collections.py) → 数据解析 → ETL转换 (services/db_service.py) → 数据模型 (models/subject.py) → 数据库
```

#### 详细流程

1. **文件上传入口**：用户通过`POST /api/v1/collections/sync/douban`接口上传豆瓣JSON文件，由`backend/app/api/v1/collections.py`中的`sync_douban_collections_endpoint`函数接收。

2. **文件读取与解析**：
   - API层读取上传的文件内容
   - 解析JSON数据，支持两种结构：包含`interest`字段的字典或直接的数据列表
   - 验证JSON格式有效性

3. **ETL数据转换**：
   - 调用`services/db_service.py`中的`convert_douban_to_bangumi`函数进行数据转换
   - 将豆瓣数据结构映射到Bangumi标准格式
   - 状态映射：`wish`→1, `collect`→2, `do`→3, `on_hold`→4, `dropped`→5
   - 类型映射：`book`→1, `movie`→6, `tv`→6, `music`→3, `game`→4

4. **统一数据入库**：
   - 调用`services/bangumi_service.py`中的`upsert_subject`函数处理Subject数据
   - 调用`_upsert_collection`函数处理Collection数据
   - 使用统一的数据库操作逻辑，确保与Bangumi数据完全兼容

5. **响应返回**：操作完成后，返回导入结果，包含成功导入的条目数量。

### 3.3 全局用户名配置流程

前端使用全局用户名配置进行数据访问的流程：

```
SettingsContext (全局配置) → 组件读取用户名 → API调用传入用户名 → 后端验证 → 数据库操作
```

#### 详细流程

1. **配置存储**：用户名存储在 SettingsContext 中，使用 localStorage 持久化
2. **组件读取**：组件通过 `useSettings` hook 读取全局用户名配置
3. **API调用**：所有需要用户名的 API 调用都传入全局用户名参数
4. **后端验证**：后端验证用户名参数是否存在，不存在则返回 400 错误
5. **数据访问**：使用传入的用户名进行数据库操作

## 4. 技术栈联动

SQLModel在本项目中同时充当了"数据库表定义"和"数据验证"的双重角色，其工作原理如下：

### SQLModel的双重角色

| 角色              | 实现方式                                  | 示例代码片段                                          |
|-------------------|-------------------------------------------|-------------------------------------------------------|
| 数据库表定义      | 通过继承SQLModel并设置`table=True`         | `class Anime(SQLModel, table=True):`                  |
| 字段类型映射      | 使用Field定义字段，指定数据库列类型        | `summary: Optional[str] = Field(sa_column=Column(Text))` |
| 数据验证          | 利用Pydantic的类型注解进行数据验证         | `name: str = Field(...)`  # 必填字符串字段            |
| 默认值设置        | 通过Field的default参数设置默认值          | `name_cn: Optional[str] = Field(default="")`         |
| 约束条件          | 使用Field的constraints参数设置约束        | `id: int = Field(primary_key=True)`                   |

### 工作机制

1. **数据库表定义**：
   - SQLModel继承了SQLAlchemy的功能，可以通过`SQLModel.metadata.create_all()`创建数据库表
   - 支持复杂的关系定义（如外键、一对一、一对多关系）
   - 可以使用SQLAlchemy的高级特性（如索引、视图等）

2. **数据验证**：
   - 继承了Pydantic的数据验证功能，自动验证输入数据的类型和约束
   - 支持自定义验证逻辑
   - 在API层面和数据库层面都能提供数据验证

3. **自动API文档**：
   - FastAPI可以自动生成API文档，包括请求参数和响应模型
   - 支持Swagger UI和ReDoc接口文档

## 5. API 职责分离与更新策略

### 5.1 API 职责分离

为了提高系统的可维护性和安全性，项目采用了 API 职责分离的设计：

| API 路径 | 职责 | 数据类型 | 认证要求 |
|---------|------|---------|---------|
| `/api/v1/subjects/` | 条目库查询 | 公有数据 | 可选 |
| `/api/v1/collections/` | 我的收藏查询与更新 | 私有数据 | 必须 |

- **`/subjects/`**：负责处理公有条目数据的查询，任何人都可以访问，无需认证。
- **`/collections/`**：负责处理用户私有收藏数据的查询和更新，必须进行用户认证。

这种设计使得 API 接口更加清晰，便于维护和扩展，同时也提高了系统的安全性，保护了用户的私有数据。

### 5.2 API 接口列表

项目提供了完整的RESTful API接口，支持Bangumi和豆瓣多数据源的数据同步和查询：

#### 5.2.1 Bangumi 数据同步接口

| 方法 | 路径 | 功能 | 认证要求 |
|------|------|------|---------|
| GET | `/api/v1/collections/sync/{username}` | 同步指定用户的Bangumi收藏数据到本地数据库 | 必须 |
| GET | `/api/v1/collections/sync/{username}?subject_type=1` | 仅同步用户的书籍收藏 | 必须 |
| GET | `/api/v1/collections/sync/{username}?subject_type=2` | 仅同步用户的动画收藏 | 必须 |
| GET | `/api/v1/collections/sync/{username}?subject_type=3` | 仅同步用户的音乐收藏 | 必须 |
| GET | `/api/v1/collections/sync/{username}?subject_type=4` | 仅同步用户的游戏收藏 | 必须 |
| GET | `/api/v1/collections/sync/{username}?subject_type=6` | 仅同步用户的三次元收藏 | 必须 |

**请求示例**：
```bash
# 同步用户所有收藏
GET /api/v1/collections/sync/myusername

# 仅同步用户的书籍收藏
GET /api/v1/collections/sync/myusername?subject_type=1
```

**响应示例**：
```json
{
  "message": "Successfully synced 42 collections for user myusername",
  "username": "myusername",
  "sync_count": 42,
  "subject_type": 1
}
```

#### 5.2.2 豆瓣数据导入接口

| 方法 | 路径 | 功能 | 认证要求 |
|------|------|------|---------|
| POST | `/api/v1/collections/sync/douban` | 从上传的JSON文件导入豆瓣收藏数据到本地数据库 | 必须 |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| file | File | 是 | 豆瓣导出的JSON文件 |
| username | string | 是 | 用户名（用于标识数据归属） |

**请求示例**：
```bash
curl -X POST "http://localhost:8000/api/v1/collections/sync/douban?username=myusername" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@douban_export.json"
```

**响应示例**：
```json
{
  "message": "Successfully imported 25 collections from Douban",
  "username": "myusername",
  "import_count": 25
}
```

#### 5.2.3 收藏查询接口

| 方法 | 路径 | 功能 | 认证要求 |
|------|------|------|---------|
| GET | `/api/v1/collections` | 获取用户的收藏列表 | 必须 |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| username | string | 是 | 用户名 |
| keyword | string | 否 | 搜索关键词 |
| type | integer | 否 | 条目类型（1=书籍, 2=动画, 3=音乐, 4=游戏, 6=三次元） |
| status | integer | 否 | 收藏状态（1=想看, 2=看完, 3=在看, 4=搁置, 5=抛弃） |
| limit | integer | 否 | 每页数量（默认20） |
| offset | integer | 否 | 偏移量（默认0） |

**请求示例**：
```bash
# 获取用户的所有收藏
GET /api/v1/collections?username=myusername

# 获取用户的动画收藏，状态为"在看"
GET /api/v1/collections?username=myusername&type=2&status=3

# 搜索包含关键词的收藏
GET /api/v1/collections?username=myusername&keyword=命运石之门
```

**响应示例**：
```json
[
  {
    "collection": {
      "id": 1,
      "user_id": 1,
      "subject_id": 12345,
      "status": 2,
      "rate": 10,
      "comment": "神作！",
      "tags": ["科幻", "悬疑"],
      "updated_at": "2024-01-01T00:00:00Z",
      "created_at": "2024-01-01T00:00:00Z"
    },
    "subject": {
      "id": 12345,
      "name": "Steins;Gate",
      "name_cn": "命运石之门",
      "type": 2,
      "cover_url": "https://lain.bgm.tv/pic/cover/l/...",
      "summary": "这是一部关于时间旅行的科幻作品...",
      "date": "2011-04-06",
      "eps": 24,
      "score": 9.5,
      "tags": ["科幻", "悬疑"],
      "meta_tags": [],
      "infobox": {},
      "rating_details": {
        "score": 9.5,
        "rank": 1
      },
      "images": {}
    }
  }
]
```

#### 5.2.4 收藏统计接口

| 方法 | 路径 | 功能 | 认证要求 |
|------|------|------|---------|
| GET | `/api/v1/collections/count` | 获取用户各类型收藏数量 | 必须 |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| username | string | 是 | 用户名 |
| subject_type | integer | 是 | 条目类型（1=书籍, 2=动画, 3=音乐, 4=游戏, 6=三次元） |

**请求示例**：
```bash
# 获取用户的动画收藏数量
GET /api/v1/collections/count?username=myusername&subject_type=2
```

**响应示例**：
```json
{
  "count": 42
}
```

#### 5.2.5 条目搜索接口

| 方法 | 路径 | 功能 | 认证要求 |
|------|------|------|---------|
| GET | `/api/v1/subjects` | 搜索条目 | 可选 |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| keyword | string | 否 | 搜索关键词 |
| type | integer | 否 | 条目类型（1=书籍, 2=动画, 3=音乐, 4=游戏, 6=三次元） |

**请求示例**：
```bash
# 搜索所有条目
GET /api/v1/subjects

# 搜索包含关键词的动画
GET /api/v1/subjects?keyword=命运石之门&type=2
```

**响应示例**：
```json
[
  {
    "id": 12345,
    "name": "Steins;Gate",
    "name_cn": "命运石之门",
    "type": 2,
    "cover_url": "https://lain.bgm.tv/pic/cover/l/...",
    "summary": "这是一部关于时间旅行的科幻作品...",
    "date": "2011-04-06",
    "eps": 24,
    "score": 9.5,
    "tags": ["科幻", "悬疑"],
    "meta_tags": [],
    "infobox": {},
    "rating_details": {
      "score": 9.5,
      "rank": 1
    },
    "images": {}
  }
]
```

#### 5.2.6 单个收藏查询接口

| 方法 | 路径 | 功能 | 认证要求 |
|------|------|------|---------|
| GET | `/api/v1/collections/{subject_id}` | 获取指定条目的收藏信息 | 必须 |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| subject_id | integer | 是 | 条目ID（路径参数） |
| username | string | 是 | 用户名（查询参数） |

**请求示例**：
```bash
GET /api/v1/collections/12345?username=myusername
```

**响应示例**：
```json
{
  "id": 1,
  "user_id": 1,
  "subject_id": 12345,
  "status": 2,
  "rate": 10,
  "comment": "神作！",
  "tags": ["科幻", "悬疑"],
  "updated_at": "2024-01-01T00:00:00Z",
  "created_at": "2024-01-01T00:00:00Z"
}
```

## 6. 核心功能说明

### 6.1 游客模式（Guest Mode）

游客模式是 OtakuNeko 的一个重要功能，允许用户在没有 Bangumi 账号的情况下使用系统。

#### 功能特性

1. **完全绕过 API 验证**：
   - 游客模式下不会调用 Bangumi API 进行用户信息验证
   - 所有数据操作都在本地进行
   - 不会触发任何网络请求到 Bangumi

2. **实时预览**：
   - 用户名输入时实时更新预览用户信息
   - 预览信息包含用户名、昵称、头像等
   - 使用本地生成的默认信息

3. **用户体验优化**：
   - 切换到游客模式时保留输入的用户名
   - 搜索按钮自动禁用
   - 防止意外触发 API 调用

4. **数据隔离**：
   - 游客模式下的数据与普通用户数据隔离
   - 使用特殊的用户标识（id=0）

#### 实现细节

游客模式在 `SettingsModal.tsx` 中的实现：

```typescript
// 游客模式切换处理
const handleGuestModeChange = useCallback((checked: boolean) => {
  setIsGuestMode(checked);
  
  if (checked) {
    const username = formData.username.trim() || 'Guest';
    const guestUser: BangumiUser = {
      id: 0,
      username: username,
      nickname: username,
      sign: '本地游客模式',
      avatar: { large: customAvatar || '', medium: customAvatar || '', small: customAvatar || '' }
    };
    setPreviewUser(guestUser);
  } else {
    setPreviewUser(null);
  }
}, [formData.username, customAvatar]);

// 用户名输入处理（游客模式下实时更新）
const handleUsernameChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
  const newUsername = e.target.value;
  setFormData(prev => ({ ...prev, username: newUsername }));
  
  if (isGuestMode) {
    const username = newUsername.trim() || 'Guest';
    const guestUser: BangumiUser = {
      id: 0,
      username: username,
      nickname: username,
      sign: '本地游客模式',
      avatar: { large: customAvatar || '', medium: customAvatar || '', small: customAvatar || '' }
    };
    setPreviewUser(guestUser);
  }
}, [isGuestMode, customAvatar]);

// 搜索用户处理（游客模式下直接返回）
const handleSearchUser = useCallback(async () => {
  if (isGuestMode) {
    return;
  }
  
  // ... 普通用户的搜索逻辑
}, [formData.username, isValidating, toast, isGuestMode]);
```

### 6.2 全局用户名配置

全局用户名配置是 OtakuNeko 的核心功能之一，确保所有数据库访问操作都使用统一的用户名。

#### 功能特性

1. **集中管理**：
   - 用户名存储在 SettingsContext 中
   - 使用 localStorage 持久化
   - 所有组件通过 `useSettings` hook 访问

2. **全局访问**：
   - 所有 API 调用都使用全局用户名
   - 同步操作使用全局用户名
   - 收藏查询使用全局用户名

3. **类型安全**：
   - 使用 TypeScript 确保类型安全
   - 所有用户名参数都是必需的
   - 编译时检查防止遗漏

#### 实现细节

SettingsContext 的实现：

```typescript
// SettingsContext.tsx
interface Settings {
  username: string;
  isGuestMode: boolean;
  customAvatar: string;
  userInfo: BangumiUser | null;
}

interface SettingsContextType {
  settings: Settings;
  updateSettings: (updates: Partial<Settings>) => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<Settings>(() => {
    const savedSettings = localStorage.getItem('otakuneko_settings');
    return savedSettings ? JSON.parse(savedSettings) : {
      username: '',
      isGuestMode: false,
      customAvatar: '',
      userInfo: null
    };
  });

  const updateSettings = useCallback((updates: Partial<Settings>) => {
    setSettings(prev => {
      const newSettings = { ...prev, ...updates };
      localStorage.setItem('otakuneko_settings', JSON.stringify(newSettings));
      return newSettings;
    });
  }, []);

  return (
    <SettingsContext.Provider value={{ settings, updateSettings }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider');
  }
  return context;
};
```

### 6.3 数据同步功能

数据同步功能允许用户从 Bangumi 同步收藏数据到本地数据库。

#### 功能特性

1. **按类型同步**：
   - 支持同步所有类型或指定类型
   - 类型包括：书籍、动画、音乐、游戏、三次元

2. **实时统计**：
   - 同步完成后自动更新收藏数量
   - 显示各类型的收藏统计

3. **错误处理**：
   - 同步失败时显示错误信息
   - 支持重试机制

#### 实现细节

syncStore 的实现：

```typescript
// syncStore.ts
interface SyncState {
  collectionCounts: {
    anime: number;
    books: number;
    games: number;
    films: number;
  };
  isSyncing: boolean;
  isLoading: boolean;
  syncError: string | null;
  lastSyncTime: Date | null;
  fetchCollectionCounts: (username: string) => Promise<void>;
  performSync: (username: string) => Promise<void>;
}

const useSyncStore = create<SyncState>((set, get) => ({
  collectionCounts: {
    anime: 0,
    books: 0,
    games: 0,
    films: 0
  },
  isSyncing: false,
  isLoading: false,
  syncError: null,
  lastSyncTime: null,

  fetchCollectionCounts: async (username: string) => {
    if (!username) {
      console.warn('Username is required for fetching collection counts');
      return;
    }
    
    set({ isLoading: true });
    try {
      const [animeCount, booksCount, gamesCount, filmsCount] = await Promise.all([
        getUserCollectionCount(username, 2),
        getUserCollectionCount(username, 1),
        getUserCollectionCount(username, 4),
        getUserCollectionCount(username, 6)
      ]);
      
      set({
        collectionCounts: {
          anime: animeCount,
          books: booksCount,
          games: gamesCount,
          films: filmsCount
        }
      });
    } catch (error) {
      console.error('Error fetching collection counts:', error);
    } finally {
      set({ isLoading: false });
    }
  },

  performSync: async (username: string) => {
    if (!username) {
      console.warn('Username is required for sync');
      set({ syncError: '用户名不能为空' });
      return;
    }
    
    const { isSyncing } = get();
    if (isSyncing) {
      console.warn('Sync is already in progress, ignoring duplicate request');
      return;
    }
    
    set({ isSyncing: true, syncError: null });
    
    try {
      await syncUser(username);
      await get().fetchCollectionCounts(username);
      set({ lastSyncTime: new Date() });
    } catch (error) {
      console.error('Sync failed:', error);
      const errorMessage = error instanceof Error ? error.message : '同步失败，请稍后重试';
      set({ syncError: errorMessage });
      throw error;
    } finally {
      set({ isSyncing: false });
    }
  }
}));
```

### 6.4 手动添加收藏

手动添加收藏功能允许用户手动添加或编辑收藏条目。

#### 功能特性

1. **条目搜索**：
   - 支持按名称搜索条目
   - 实时显示搜索结果
   - 防抖优化性能

2. **收藏编辑**：
   - 支持编辑已有收藏
   - 支持设置评分、评论、标签
   - 支持设置收藏状态

3. **表单验证**：
   - 必填字段验证
   - 数据格式验证

#### 实现细节

ManualAddDialog 的实现：

```typescript
// ManualAddDialog.tsx
const ManualAddDialog: React.FC = () => {
  const { settings } = useSettings();
  const [searchResults, setSearchResults] = useState<Subject[]>([]);
  const [formData, setFormData] = useState({
    rate: 0,
    comment: '',
    tags: '',
    status: 1
  });

  const handleSearch = useCallback(async (keyword: string) => {
    if (!keyword) {
      setSearchResults([]);
      return;
    }
    
    const results = await searchSubjects(keyword);
    setSearchResults(results);
  }, []);

  const handleSave = async () => {
    if (!settings.username) {
      toast({ type: 'error', message: '请先设置用户名' });
      return;
    }

    try {
      await api.post('/collections', {
        username: settings.username,
        subject_id: selectedSubject.id,
        rate: formData.rate,
        comment: formData.comment,
        tags: formData.tags.split(',').map(t => t.trim()),
        status: formData.status
      });
      
      toast({ type: 'success', message: '保存成功' });
      closeDialog();
    } catch (error) {
      toast({ type: 'error', message: '保存失败' });
    }
  };

  return (
    <Dialog>
      <SearchInput onSearch={handleSearch} />
      <SearchResults results={searchResults} onSelect={handleSelectSubject} />
      <Form data={formData} onChange={setFormData} />
      <Buttons onSave={handleSave} onCancel={closeDialog} />
    </Dialog>
  );
};
```

### 6.5 豆瓣数据导入

豆瓣数据导入功能允许用户从豆瓣导出的 JSON 文件导入收藏数据。

#### 功能特性

1. **文件上传**：
   - 支持 JSON 文件上传
   - 文件大小限制
   - 文件格式验证

2. **数据转换**：
   - 自动转换豆瓣数据格式
   - 状态映射
   - 类型映射

3. **导入反馈**：
   - 显示导入进度
   - 显示导入结果
   - 错误提示

#### 实现细节

DoubanImportDialog 的实现：

```typescript
// DoubanImportDialog.tsx
const DoubanImportDialog: React.FC = () => {
  const { settings } = useSettings();
  const [file, setFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleImport = async () => {
    if (!file) {
      toast({ type: 'error', message: '请选择文件' });
      return;
    }

    if (!settings.username) {
      toast({ type: 'error', message: '请先设置用户名' });
      return;
    }

    setIsImporting(true);
    try {
      const result = await uploadDoubanFile(file, settings.username);
      toast({ 
        type: 'success', 
        message: `成功导入 ${result.import_count} 条数据` 
      });
      closeDialog();
    } catch (error) {
      toast({ type: 'error', message: '导入失败' });
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <Dialog>
      <FileInput onChange={handleFileSelect} />
      <ImportButton onClick={handleImport} disabled={isImporting} />
    </Dialog>
  );
};
```

## 7. 组件交互流程

### 7.1 用户设置流程

```
用户打开设置 → 显示当前设置 → 用户修改设置 → 保存到 SettingsContext → 持久化到 localStorage → 更新相关组件
```

#### 详细流程

1. **打开设置**：用户点击 Header 中的设置按钮
2. **显示设置**：SettingsModal 显示当前设置（用户名、游客模式、头像等）
3. **修改设置**：
   - 输入用户名
   - 切换游客模式
   - 上传自定义头像
4. **保存设置**：
   - 普通模式：验证用户名并保存
   - 游客模式：直接保存，不验证
5. **持久化**：设置保存到 localStorage
6. **更新组件**：相关组件自动更新（Header、同步功能等）

### 7.2 数据同步流程

```
用户点击同步按钮 → 检查用户名 → 调用同步 API → 更新收藏统计 → 显示同步结果
```

#### 详细流程

1. **点击同步**：用户在 Header 中点击"一键同步"按钮
2. **检查用户名**：
   - 如果没有用户名，提示用户先设置
   - 如果有用户名，继续同步
3. **调用同步 API**：
   - 调用 `syncUser(username)` 函数
   - 后端从 Bangumi 获取数据
   - 数据转换并保存到数据库
4. **更新统计**：
   - 调用 `fetchCollectionCounts(username)` 函数
   - 更新各类型收藏数量
   - 更新最后同步时间
5. **显示结果**：
   - 成功：显示成功提示
   - 失败：显示错误信息

### 7.3 搜索条目流程

```
用户输入搜索关键词 → 防抖处理 → 调用搜索 API → 显示搜索结果 → 用户选择条目
```

#### 详细流程

1. **输入关键词**：用户在搜索框输入关键词
2. **防抖处理**：等待用户停止输入（300ms）
3. **调用搜索 API**：
   - 调用 `searchSubjects(keyword)` 函数
   - 后端返回匹配的条目列表
4. **显示结果**：
   - 在下拉菜单中显示搜索结果
   - 显示条目名称、评分等信息
5. **选择条目**：
   - 用户点击条目
   - 根据当前页面执行不同操作：
     - 收藏页面：打开手动添加对话框
     - 其他页面：设置为聊天上下文

## 8. 最佳实践

### 8.1 组件设计原则

1. **单一职责**：每个组件只负责一个功能
2. **可复用性**：UI 组件应该高度可复用
3. **类型安全**：使用 TypeScript 确保类型安全
4. **性能优化**：使用 React Compiler 和 useCallback/useMemo 优化性能

### 8.2 状态管理原则

1. **就近原则**：状态应该放在离使用它最近的地方
2. **全局状态**：使用 Zustand 管理全局状态
3. **Context 使用**：使用 React Context 管理配置和主题
4. **持久化**：需要持久化的状态使用 localStorage

### 8.3 API 调用原则

1. **统一入口**：所有 API 调用通过 api.ts 统一管理
2. **错误处理**：统一的错误处理机制
3. **类型定义**：使用 TypeScript 定义请求和响应类型
4. **用户反馈**：API 调用结果需要给用户反馈

### 8.4 用户体验原则

1. **加载状态**：所有异步操作都需要显示加载状态
2. **错误提示**：所有错误都需要给用户明确的提示
3. **防抖节流**：输入类操作使用防抖优化
4. **无障碍**：组件需要支持键盘导航和屏幕阅读器

## 9. 已知问题与解决方案

### 9.1 已解决的问题

1. **Checkbox 组件问题**：
   - 问题：勾选后的对勾图标不居中，点击复选框没有反应
   - 解决：使用 Flexbox 布局居中图标，添加点击处理函数

2. **游客模式 API 调用问题**：
   - 问题：游客模式下仍然会触发 API 调用
   - 解决：在 handleSearchUser 函数开头添加游客模式检查

3. **Header 组件空字符串 src 属性错误**：
   - 问题：userInfo.avatar.large 为空字符串时导致浏览器警告
   - 解决：检查 userInfo?.avatar?.large 是否存在且有值

4. **硬编码用户名问题**：
   - 问题：多个地方硬编码了用户名 'hacci'
   - 解决：实现全局用户名配置，所有地方使用 SettingsContext

### 9.2 待优化项

1. **性能优化**：
   - 大量数据时的虚拟滚动
   - 图片懒加载优化
   - 代码分割优化

2. **功能增强**：
   - 批量操作功能
   - 导出功能
   - 高级筛选功能

3. **用户体验**：
   - 离线模式支持
   - 数据缓存策略
   - 更好的错误恢复机制

## 10. 更新日志

### 2025-12-28

#### Bug 修复

1. **405 Method Not Allowed 错误**
   - 修复了 ManualAddDialog 提交数据时的 405 错误
   - 将错误的 API 端点从 `POST /collections/{subject_id}` 改为正确的 `POST /collections/manual`
   - 在请求体中添加 `subject_id` 字段来关联已存在的条目
   - 重构了 ManualAddDialog 组件，使用新的 `createManualCollection` API 函数

2. **用户注册接口优化**
   - 修改了 `register_local_user` 接口实现 Upsert 逻辑
   - 当用户名已存在且为本地用户时，支持更新 `bangumi_id` 和 `avatar_url` 字段
   - 添加了 `update_needed` 标志，避免不必要的数据库写入
   - 添加了详细的日志输出，便于追踪更新操作

#### API 改进

1. **新增 API 函数**
   - 在 `api.ts` 中添加了 `createManualCollection` 函数
   - 定义了 `ManualCollectionData` 接口，规范手动收藏数据结构
   - 统一了手动收藏创建的 API 调用方式

2. **用户注册接口增强**
   - 实现了"存在即更新 (Upsert)"策略
   - 支持覆盖 Bangumi ID 和头像信息
   - 优化了数据库提交逻辑，提高性能

#### 代码质量

1. **代码重构**
   - 提取了 `createManualCollection` 函数，提高代码复用性
   - 优化了 ManualAddDialog 的 API 调用逻辑
   - 统一了错误处理机制

2. **日志增强**
   - 添加了详细的操作日志
   - 便于问题追踪和调试

### 2025-12-27

#### 新增功能

1. **游客模式（Guest Mode）**
   - 实现了完整的游客模式功能
   - 游客模式下完全绕过 API 验证
   - 支持实时预览用户信息
   - 优化了用户体验，保留输入的用户名

2. **全局用户名配置**
   - 实现了 SettingsContext 全局配置管理
   - 所有数据库访问操作使用全局用户名
   - 移除了所有硬编码的用户名
   - 添加了用户名验证机制

3. **数据同步功能**
   - 实现了 syncStore 状态管理
   - 实现了 useSync 自定义 Hook
   - 支持按类型同步数据
   - 支持实时统计收藏数量

4. **手动添加收藏**
   - 实现了 ManualAddDialog 组件
   - 支持条目搜索功能
   - 支持编辑已有收藏
   - 使用全局用户名配置

5. **豆瓣数据导入**
   - 实现了 DoubanImportDialog 组件
   - 支持文件上传功能
   - 支持数据格式转换
   - 显示导入进度和结果

6. **UI 组件增强**
   - 实现了 Checkbox 组件，支持无障碍访问
   - 实现了 NavPillSkeleton 骨架屏组件
   - 实现了 CollectionGridPage 收藏网格页面
   - 优化了 Header 组件，修复了空字符串 src 属性错误

#### Bug 修复

1. **Checkbox 组件问题**
   - 修复了对勾图标不居中的问题
   - 修复了点击复选框没有反应的问题
   - 添加了完整的无障碍支持（ARIA 属性、键盘导航）

2. **游客模式 API 调用问题**
   - 修复了游客模式下仍然触发 API 调用的问题
   - 添加了多层防护机制
   - 优化了搜索按钮的禁用逻辑

3. **Header 组件问题**
   - 修复了空字符串 src 属性导致的浏览器警告
   - 优化了头像显示逻辑

4. **硬编码用户名问题**
   - 移除了所有硬编码的用户名 'hacci'
   - 统一使用全局用户名配置
   - 添加了用户名参数验证

#### 架构改进

1. **状态管理优化**
   - 使用 Zustand 实现轻量级全局状态管理
   - 实现了 syncStore 和 manualAddDialogStore
   - 优化了状态更新逻辑

2. **API 调用优化**
   - 统一了 API 调用入口
   - 添加了用户名参数验证
   - 优化了错误处理机制

3. **组件复用性**
   - 提取了可复用的 UI 组件
   - 优化了组件接口设计
   - 提高了代码复用率

#### 文档更新

1. 更新了架构报告，添加了新功能的详细说明
2. 添加了组件交互流程图
3. 添加了最佳实践指南
4. 添加了已知问题与解决方案章节
5. 添加了更新日志

---

## 附录

### A. 类型定义汇总

```typescript
// Dashboard 统计数据
interface DashboardStats {
  total_subjects: number;
  total_collections: number;
  system_status: string;
  recent_activity: RecentActivityItem[];
}

// 最近活动项
interface RecentActivityItem {
  id: string;
  user_id: number;
  subject_id: number;
  subject_name: string;
  subject_type: number;
  collection_type: number;
  updated_at: string;
}

// 条目数据
interface Subject {
  id: number;
  name: string;
  name_cn: string;
  type: number;
  cover_url: string;
  summary: string;
  date: string;
  platform?: string;
  eps?: number;
  volumes?: number;
  score?: number;
  rank?: number;
  collection_total?: number;
  tags: string[];
  meta_tags: string[];
  infobox: Record<string, string>;
  rating_details: Record<string, any>;
  images: Record<string, any>;
}

// 收藏数据
interface Collection {
  id: number;
  user_id: number;
  subject_id: number;
  status: number;
  rate: number;
  comment: string;
  tags: string[];
  updated_at: string;
  created_at: string;
}

// 收藏+条目数据
interface CollectionWithSubject {
  collection: Collection;
  subject: Subject;
}

// Bangumi 用户信息
interface BangumiUser {
  id: number;
  username: string;
  nickname: string;
  sign: string;
  avatar: {
    large: string;
    medium: string;
    small: string;
  };
}

// 设置信息
interface Settings {
  username: string;
  isGuestMode: boolean;
  customAvatar: string;
  userInfo: BangumiUser | null;
}

// 同步状态
interface SyncState {
  collectionCounts: {
    anime: number;
    books: number;
    games: number;
    films: number;
  };
  isSyncing: boolean;
  isLoading: boolean;
  syncError: string | null;
  lastSyncTime: Date | null;
}
```

### B. 状态码说明

| 状态码 | 说明 | 用途 |
|--------|------|------|
| 1 | 想看 | 用户计划观看/阅读的条目 |
| 2 | 看完 | 用户已经看完/读完的条目 |
| 3 | 在看 | 用户正在观看/阅读的条目 |
| 4 | 搁置 | 用户暂时搁置的条目 |
| 5 | 抛弃 | 用户放弃的条目 |

### C. 条目类型说明

| 类型码 | 说明 | 英文名称 |
|--------|------|----------|
| 1 | 书籍 | book |
| 2 | 动画 | anime |
| 3 | 音乐 | music |
| 4 | 游戏 | game |
| 6 | 三次元 | real |

### D. 环境变量配置

```env
# 后端配置
DATABASE_URL=postgresql://user:password@localhost:5432/otakuneko
BANGUMI_API_URL=https://api.bgm.tv

# 前端配置
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_APP_NAME=OtakuNeko
```

### E. 开发指南

#### 前端开发

1. **安装依赖**：
```bash
cd frontend
npm install
```

2. **启动开发服务器**：
```bash
npm run dev
```

3. **类型检查**：
```bash
npm run typecheck
```

4. **代码检查**：
```bash
npm run lint
```

#### 后端开发

1. **安装依赖**：
```bash
cd backend
pip install -r requirements.txt
```

2. **启动开发服务器**：
```bash
uvicorn app.main:app --reload
```

3. **运行测试**：
```bash
pytest
```

#### Docker 部署

1. **构建镜像**：
```bash
docker-compose build
```

2. **启动服务**：
```bash
docker-compose up -d
```

3. **查看日志**：
```bash
docker-compose logs -f
```

4. **停止服务**：
```bash
docker-compose down
```

---

**文档版本**: 2.0  
**最后更新**: 2024-12-27  
**维护者**: OtakuNeko 开发团队
