# OtakuNeko 前端文档

## 目录
- [概述](#概述)
- [项目架构](#项目架构)
- [目录结构](#目录结构)
- [核心组件](#核心组件)
- [API 层](#api-层)
- [状态管理](#状态管理)
- [样式系统](#样式系统)
- [上下文提供者](#上下文提供者)
- [自定义 Hooks](#自定义-hooks)
- [设计模式](#设计模式)
- [最佳实践](#最佳实践)

---

## 概述

OtakuNeko 是一个基于 Next.js 16.1.0 (Turbopack)、React 和 TypeScript 构建的 AI 驱动动漫仪表板。该应用为用户提供了一个综合平台,用于管理动漫收藏、参与 AI 驱动的对话,以及与 Bangumi 和豆瓣等外部服务同步数据。

### 核心功能
- **AI 驱动的聊天**: 具有打字效果和消息管理的交互式聊天界面
- **收藏管理**: 基于网格的动画、游戏和书籍展示,支持筛选和搜索
- **数据同步**: 与 Bangumi API 和豆瓣导入功能的集成
- **主题系统**: 多种视觉主题(默认、海洋、樱花),使用 CSS 自定义属性
- **响应式设计**: 移动优先的自适应布局方法
- **类型安全**: 完整的 TypeScript 实现,增强开发者体验

---

## 项目架构

### 技术栈
- **框架**: Next.js 16.1.0 (App Router with Turbopack)
- **UI 库**: React with TypeScript
- **样式**: Tailwind CSS with custom theme variables
- **状态管理**: React Context API + Zustand
- **HTTP 客户端**: Axios
- **图标**: Lucide React
- **字体**: Geist Sans and Geist Mono (Google Fonts)

### 应用结构

应用遵循 Next.js App Router 约定,对交互式组件采用客户端渲染方法。架构分为三个主要层次:

1. **展示层**: `src/components/` 中的组件
2. **业务逻辑层**: `src/hooks/` 中的 hooks 和 `src/contexts/` 中的上下文
3. **数据层**: `src/lib/api.ts` 中的 API 函数和 `src/lib/` 中的 stores

---

## 目录结构

```
frontend/src/
├── app/                          # Next.js App Router 页面
│   ├── api/                      # API 路由
│   │   └── collections/
│   │       └── route.ts         # 收藏代理端点
│   ├── collections/
│   │   └── page.tsx             # 收藏网格页面
│   ├── globals.css              # 全局样式和主题定义
│   ├── layout.tsx               # 带有提供者的根布局
│   └── page.tsx                 # 首页(聊天界面)
├── components/                   # React 组件
│   ├── chat/                     # 聊天相关组件
│   │   ├── ChatInput.tsx        # 聊天输入组件，支持自动调整大小、模型选择、角色选择
│   │   ├── EmptyState.tsx       # 空状态显示，当无收藏同步时显示引导信息
│   │   ├── MessageAttachment.tsx # 消息附件显示组件
│   │   ├── MessageBubble.tsx    # 消息气泡组件，支持打字效果、上下文解析、重试功能
│   │   ├── MessageSkeleton.tsx  # 消息加载骨架屏
│   │   └── ToolsPanel.tsx       # 工具面板，用于启用/禁用聊天工具
│   ├── dashboard/               # 仪表板组件
│   │   ├── AICoreStatus.tsx    # AI 核心状态显示，包含数据可视化图表
│   │   ├── AnalysisInsights.tsx # 分析洞察组件，使用 Recharts 展示数据分析
│   │   ├── AnimationManager.tsx # 动画管理器组件
│   │   ├── PluginManager.tsx   # 插件管理器组件
│   │   └── SyncCard.tsx        # 同步卡片，显示收藏计数和同步控制
│   ├── layout/                   # 布局组件(Header, Sidebar)
│   │   ├── Header.tsx      # 主 Header 组件，包含搜索、用户信息、主题切换
│   │   └── Sidebar.tsx         # 侧边栏导航组件，持久化显示
│   ├── settings/                 # 设置相关组件
│   │   ├── DoubanImportDialog.tsx # 豆瓣导入对话框，支持 CSV 文件上传
│   │   ├── GridImportModal.tsx  # 网格导入模态框
│   │   ├── ManualAddDialog.tsx  # 手动添加收藏对话框
│   │   └── SettingsModal.tsx    # 设置模态框，包含用户设置界面
│   └── ui/                       # 可重用 UI 组件
│       ├── Badge.tsx           # 徽章组件，支持多种变体和状态
│       ├── Button.tsx          # 按钮组件，支持 default、outline、ghost 变体
│       ├── Card.tsx            # 卡片容器组件，带阴影和圆角
│       ├── Checkbox.tsx        # 复选框组件，支持 indeterminate 状态
│       ├── Dialog.tsx          # 模态对话框组件，支持动画和可访问性
│       ├── Input.tsx           # 文本输入组件，支持图标、验证状态
│       ├── Label.tsx           # 表单标签组件，支持关联输入框
│       ├── NavPillSkeleton.tsx # 导航药丸骨架屏加载状态
│       ├── PosterCard.tsx      # 海报显示卡片，用于收藏项展示
│       ├── Select.tsx          # 下拉选择组件，支持分组、搜索、清除功能
│       ├── SortDropdown.tsx    # 排序下拉菜单组件
│       ├── Switch.tsx         # 切换开关组件，支持加载状态和多种变体
│       ├── Tabs.tsx            # 选项卡导航组件，支持键盘导航
│       ├── Textarea.tsx        # 多行文本输入，支持字符计数和调整大小
│       ├── ThemeSwitcher.tsx   # 主题切换组件，支持多种主题预览
│       └── Toast.tsx           # Toast 通知系统，支持多种类型和位置
├── contexts/                     # React Context 提供者
│   ├── ChatContext.tsx          # 聊天状态管理
│   ├── HeaderContext.tsx        # Header 状态管理
│   └── SettingsContext.tsx       # 设置和用户数据
├── hooks/                        # 自定义 React hooks
│   ├── useDebounce.ts           # 防抖实用 hook
│   └── useSync.ts               # 同步功能 hook
└── lib/                          # 实用工具库
    ├── api.ts                   # API 客户端和函数
    ├── image-config.ts          # 图片优化配置
    ├── logger.ts                # 日志工具
    ├── manualAddDialogStore.ts  # 手动添加对话框状态
    ├── settingsHelper.ts        # 设置工具
    ├── syncStore.ts             # 同步状态管理(Zustand)
    └── utils.ts                 # 通用工具函数
```

---

## 组件开发指南

### 组件架构原则

OtakuNeko 前端采用模块化、可重用的组件架构设计。所有组件遵循以下核心原则：

1. **单一职责**: 每个组件只负责一个明确的功能
2. **可组合性**: 组件设计为可组合的构建块
3. **类型安全**: 所有组件使用 TypeScript 进行严格类型定义
4. **可访问性**: 遵循 WCAG 2.1 标准，确保键盘导航和屏幕阅读器支持
5. **性能优化**: 使用 React.memo、useMemo 和 useCallback 避免不必要的重渲染
6. **主题一致性**: 所有颜色和样式通过主题变量管理，避免硬编码

### 组件分类

#### 1. 布局组件 (Layout Components)

**位置**: `components/layout/`

**用途**: 提供应用的整体结构和导航框架

**关键组件**:
- **Header**: 持久化头部，包含搜索、用户信息、主题切换
- **Sidebar**: 侧边栏导航，提供主要功能入口

**设计模式**:
```typescript
// 布局组件应保持无状态或最小化状态
// 使用 Context API 管理跨组件状态
interface LayoutProps {
  children: React.ReactNode;
  className?: string;
}

export const Layout: React.FC<LayoutProps> = ({ children, className }) => {
  return (
    <div className={cn("flex h-screen bg-background", className)}>
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
};
```

**最佳实践**:
- 布局组件应使用 `usePathname()` 进行活动路由检测
- 避免在布局组件中直接调用 API，通过 hooks 封装
- 使用 `useHeaderContext()` 管理跨页面的共享状态
- 确保布局组件在页面转换时保持持久化

#### 2. 页面组件 (Page Components)

**位置**: `app/[route]/page.tsx`

**用途**: 定义应用的主要页面和路由

**设计模式**:
```typescript
// 页面组件应包含完整的业务逻辑
export default function Page() {
  const [state, setState] = useState(initialState);
  const { data, loading, error } = useCustomHook();

  useEffect(() => {
    // 初始化逻辑
  }, []);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState />;

  return (
    <div className="container mx-auto p-4">
      {/* 页面内容 */}
    </div>
  );
}
```

**最佳实践**:
- 页面组件应该是客户端组件（使用 'use client' 指令）
- 使用自定义 hooks 封装业务逻辑和 API 调用
- 实现适当的加载和错误状态
- 使用 Next.js Image 组件优化图片加载
- 实现响应式设计，支持移动端和桌面端

#### 3. 功能组件 (Feature Components)

**位置**: `components/chat/`, `components/dashboard/`, `components/settings/`

**用途**: 实现特定的业务功能和交互

**设计模式**:
```typescript
// 功能组件应接收明确的 props 接口
interface FeatureComponentProps {
  data: DataType[];
  onAction: (id: string) => void;
  isLoading?: boolean;
  className?: string;
}

export const FeatureComponent: React.FC<FeatureComponentProps> = ({
  data,
  onAction,
  isLoading,
  className,
}) => {
  const [localState, setLocalState] = useState<LocalStateType>(initialState);

  const handleAction = useCallback((id: string) => {
    onAction(id);
  }, [onAction]);

  if (isLoading) return <Skeleton />;

  return (
    <div className={cn("feature-container", className)}>
      {data.map(item => (
        <ItemComponent key={item.id} item={item} onAction={handleAction} />
      ))}
    </div>
  );
};
```

**最佳实践**:
- 使用明确的 TypeScript 接口定义 props
- 使用 `useCallback` 缓存事件处理函数
- 使用 `useMemo` 缓存计算结果
- 实现适当的加载和空状态
- 使用 `cn()` 工具函数合并类名

#### 4. UI 组件 (UI Components)

**位置**: `components/ui/`

**用途**: 提供可重用的基础 UI 元素

**设计模式**:
```typescript
// UI 组件应使用 Class Variance Authority (CVA) 管理变体
import { cva, type VariantProps } from 'class-variance-authority';

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
```

**最佳实践**:
- 使用 CVA 管理组件变体
- 使用 `forwardRef` 支持引用传递
- 扩展原生 HTML 元素的 props 接口
- 支持主题变量，避免硬编码颜色
- 实现完整的 ARIA 属性支持
- 提供清晰的 TypeScript 类型定义

### 状态管理策略

#### 1. 本地状态 (Local State)

**使用场景**: 组件内部的状态，不需要跨组件共享

**实现方式**:
```typescript
const [count, setCount] = useState(0);
const [items, setItems] = useState<Item[]>([]);
```

**最佳实践**:
- 优先使用本地状态，避免过度使用全局状态
- 使用 TypeScript 定义状态类型
- 使用 `useReducer` 处理复杂状态逻辑

#### 2. Context 状态 (Context State)

**使用场景**: 需要在多个组件之间共享的状态

**实现方式**:
```typescript
// 创建 Context
const MyContext = createContext<MyContextType | undefined>(undefined);

// 创建 Provider
export const MyProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState(initialState);

  const value = useMemo(() => ({
    state,
    setState,
  }), [state]);

  return (
    <MyContext.Provider value={value}>
      {children}
    </MyContext.Provider>
  );
};

// 创建自定义 Hook
export const useMyContext = () => {
  const context = useContext(MyContext);
  if (!context) {
    throw new Error('useMyContext must be used within MyProvider');
  }
  return context;
};
```

**最佳实践**:
- 将 Context 拆分为多个小型的 Context，避免单个 Context 过大
- 使用自定义 Hook 封装 Context 访问逻辑
- 在 Provider 中使用 `useMemo` 优化 context 值
- 确保提供者层次结构正确，避免 Context 访问错误

#### 3. Zustand 状态 (Zustand State)

**使用场景**: 需要持久化或复杂状态管理的场景

**实现方式**:
```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface MyStore {
  items: Item[];
  addItem: (item: Item) => void;
  removeItem: (id: string) => void;
  clearItems: () => void;
}

export const useMyStore = create<MyStore>()(
  persist(
    (set) => ({
      items: [],
      addItem: (item) => set((state) => ({ items: [...state.items, item] })),
      removeItem: (id) => set((state) => ({ items: state.items.filter(i => i.id !== id) })),
      clearItems: () => set({ items: [] }),
    }),
    {
      name: 'my-store-storage',
    }
  )
);
```

**最佳实践**:
- 使用 Zustand 管理需要持久化的状态
- 使用中间件（如 persist）扩展 store 功能
- 将状态更新逻辑封装在 actions 中
- 使用 TypeScript 定义完整的 store 接口

### 样式系统

#### 主题变量

所有颜色和样式通过 CSS 自定义属性（CSS Variables）管理：

```css
:root {
  /* 基础颜色 */
  --background: #ffffff;
  --foreground: #0a0a0a;
  
  /* 主题颜色 */
  --primary: #ff6b35;
  --primary-foreground: #ffffff;
  
  /* 状态颜色 */
  --success: #22c55e;
  --warning: #f59e0b;
  --error: #ef4444;
  
  /* 边框和背景 */
  --border: #e5e7eb;
  --input: #e5e7eb;
  --ring: #ff6b35;
  
  /* 聊天气泡 */
  --bg-bubble-user: #ff6b35;
  --bg-bubble-assistant: #f3f4f6;
}

[data-theme='ocean'] {
  --primary: #0ea5e9;
  --primary-foreground: #ffffff;
}

[data-theme='sakura'] {
  --primary: #ec4899;
  --primary-foreground: #ffffff;
}
```

#### Tailwind CSS 配置

使用 Tailwind CSS 进行样式开发，配置主题变量：

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: {
          DEFAULT: 'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        success: 'var(--success)',
        warning: 'var(--warning)',
        error: 'var(--error)',
      },
    },
  },
};
```

#### 样式最佳实践

1. **使用主题变量**:
```typescript
// ✅ 正确
<div className="bg-background text-foreground border-border" />

// ❌ 错误
<div className="bg-white text-black border-gray-200" />
```

2. **使用 cn() 工具函数**:
```typescript
import { cn } from '@/lib/utils';

<div className={cn(
  "base-classes",
  isActive && "active-classes",
  className
)} />
```

3. **响应式设计**:
```typescript
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
  {/* 响应式网格 */}
</div>
```

4. **暗色模式支持**:
```typescript
<div className="bg-background dark:bg-gray-900 text-foreground dark:text-gray-100">
  {/* 暗色模式适配 */}
</div>
```

### 可访问性指南

所有组件应遵循 WCAG 2.1 标准：

#### 键盘导航

```typescript
// 支持键盘交互
<button
  onClick={handleClick}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      handleClick();
    }
  }}
  aria-label="Button label"
>
  Button
</button>
```

#### ARIA 属性

```typescript
// 使用 ARIA 属性增强可访问性
<div
  role="button"
  tabIndex={0}
  aria-pressed={isActive}
  aria-label="Toggle button"
  onClick={handleClick}
  onKeyDown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      handleClick();
    }
  }}
>
  Toggle
</div>
```

#### 表单关联

```typescript
// 使用 htmlFor 关联标签和输入框
<Label htmlFor="email">Email</Label>
<Input
  id="email"
  type="email"
  aria-describedby="email-description"
  aria-invalid={hasError}
  aria-errormessage="email-error"
/>
<p id="email-description" className="text-sm text-muted-foreground">
  Enter your email address
</p>
{hasError && <p id="email-error" className="text-sm text-error">Invalid email</p>}
```

#### 焦点管理

```typescript
// 使用 ref 管理焦点
const inputRef = useRef<HTMLInputElement>(null);

useEffect(() => {
  if (isOpen) {
    inputRef.current?.focus();
  }
}, [isOpen]);

<input ref={inputRef} />
```

### 性能优化

#### 1. 使用 React.memo

```typescript
export const MyComponent = React.memo<MyComponentProps>(({ data, onClick }) => {
  return <div onClick={onClick}>{data.map(item => <Item key={item.id} />)}</div>;
});
```

#### 2. 使用 useMemo

```typescript
const filteredItems = useMemo(() => {
  return items.filter(item => item.status === 'active');
}, [items]);
```

#### 3. 使用 useCallback

```typescript
const handleClick = useCallback((id: string) => {
  onItemClick(id);
}, [onItemClick]);
```

#### 4. 代码分割

```typescript
// 使用动态导入进行代码分割
const HeavyComponent = dynamic(() => import('./HeavyComponent'), {
  loading: () => <Skeleton />,
  ssr: false,
});
```

#### 5. 图片优化

```typescript
// 使用 Next.js Image 组件
import Image from 'next/image';

<Image
  src={posterUrl}
  alt={title}
  width={300}
  height={450}
  loading="lazy"
  placeholder="blur"
  blurDataURL="data:image/jpeg;base64,..."
/>
```

### 组件集成指南

#### 1. 使用 Context Provider

确保组件在正确的 Provider 层级中使用：

```typescript
// layout.tsx
<SettingsProvider>
  <ToastProvider>
    <ChatProvider>
      <HeaderProvider>
        <Header />
        <main>{children}</main>
      </HeaderProvider>
    </ChatProvider>
  </ToastProvider>
</SettingsProvider>
```

#### 2. 使用自定义 Hooks

封装业务逻辑到自定义 hooks：

```typescript
// hooks/useMyFeature.ts
export function useMyFeature() {
  const [data, setData] = useState<DataType[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getData();
      setData(result);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

// 在组件中使用
function MyComponent() {
  const { data, loading, error, refetch } = useMyFeature();

  if (loading) return <Skeleton />;
  if (error) return <ErrorState onRetry={refetch} />;

  return <div>{/* 渲染数据 */}</div>;
}
```

#### 3. 错误处理

实现统一的错误处理机制：

```typescript
// 使用 Error Boundary
class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || <ErrorFallback />;
    }
    return this.props.children;
  }
}

// 使用 Toast 显示错误
const { error } = useToast();

try {
  await apiCall();
} catch (err) {
  error('操作失败', err.message);
}
```

### 测试指南

#### 单元测试

```typescript
// 使用 React Testing Library
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from './Button';

describe('Button', () => {
  it('renders correctly', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const handleClick = jest.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    fireEvent.click(screen.getByText('Click me'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
```

---

## 核心组件

### 布局组件

#### 根布局 ([`layout.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/layout.tsx))

根布局定义了应用结构和提供者层次结构。它负责:

1. **字体配置**: 加载 Geist Sans 和 Geist Mono 字体
2. **主题初始化**: 注入脚本以从 localStorage 恢复保存的主题
3. **提供者层次结构**: 以正确的顺序用上下文提供者包装应用

**提供者层次结构**:
```tsx
<SettingsProvider>
  <ToastProvider>
    <ChatProvider>
      <HeaderProvider>
        <Header />
        <main>{children}</main>
      </HeaderProvider>
    </ChatProvider>
  </ToastProvider>
</SettingsProvider>
```

**关键设计决策**: 提供者顺序至关重要。`SettingsProvider` 必须是最外层的,因为它被 `useSync` 使用,而 `useSync` 在 `Header` 组件中被调用。`ChatProvider` 必须包装 `Header`,因为 Header 使用 `useChatContext`。

#### 侧边栏 ([`Sidebar.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/layout/Sidebar.tsx))

一个持久的导航组件,提供对不同应用部分的访问:

**功能**:
- 使用 `usePathname` hook 进行活动路由高亮
- 带有图标的响应式导航菜单
- 链接到: Chat、Collections、Tools、Role、Settings

**导航项**:
```typescript
[
  { icon: <MessageSquare />, label: 'Chat', href: '/' },
  { icon: <Grid />, label: 'Collections', href: '/collections' },
  { icon: <Wrench />, label: 'Tools', href: '/tools' },
  { icon: <UserCircle />, label: 'Role', href: '#' },
  { icon: <Settings />, label: 'Settings', href: '/settings' },
]
```

#### 头部 ([`Header.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/layout/Header/Header.tsx))

一个综合头部组件,提供:

**核心功能**:
- 带实时下拉的搜索功能
- 用户同步状态和收藏计数
- 主题切换功能
- 设置模态框触发器
- 网格导入和手动添加对话框

**状态管理**:
使用 `HeaderContext` 在页面转换间保持持久状态:
```typescript
const {
  searchQuery,
  setSearchQuery,
  searchResults,
  setSearchResults,
  isSearchDropdownOpen,
  setIsSearchDropdownOpen,
  isSearching,
  setIsSearching,
  isPopoverOpen,
  setIsPopoverOpen,
  isSettingsOpen,
  setIsSettingsOpen,
  isGridImportOpen,
  setIsGridImportOpen,
  clearSearch,
} = useHeaderContext();
```

**依赖项**:
- `useSync`: 用于收藏计数和同步功能
- `useChatContext`: 用于设置参考项
- `useSettings`: 用于用户信息和设置
- `useManualAddDialogStore`: 用于手动添加对话框状态

### 页面组件

#### 首页 ([`page.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/page.tsx))

主要的聊天界面页面,具有以下功能:

**状态管理**:
```typescript
const [messages, setMessages] = useState<Message[]>([]);
const [isLoading, setIsLoading] = useState(true);
```

**消息接口**:
```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;              // 助手消息的完整内容
  currentContent: string;        // 当前显示的内容(打字效果)
  status: 'sending' | 'sent' | 'error';
  timestamp: string;
}
```

**核心功能**:

1. **初始化**: 如果用户已认证,则在挂载时获取收藏计数
2. **打字效果**: 逐字符显示模拟 AI 响应
3. **消息重试**: 允许重试失败的助手消息
4. **空状态**: 当没有消息时显示欢迎屏幕
5. **加载状态**: 在检查已同步主题时显示加载动画

**条件渲染**:
- 加载状态: 加载动画
- 无已同步主题: `EmptyState` 组件
- 有已同步主题: 带有消息和输入的聊天界面

#### 收藏页面 ([`page.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/collections/page.tsx))

一个综合的基于网格的收藏管理页面:

**Props 接口**:
```typescript
interface CollectionGridPageProps {
  items?: CollectionItem[];
  onAddItem?: () => void;
  onItemClick?: (item: CollectionItem) => void;
  fetchItems?: () => Promise<CollectionItem[]>;
  className?: string;
}
```

**收藏项接口**:
```typescript
export interface CollectionItem {
  id: number;
  title: string;
  posterUrl: string;
  rating: number;
  status: string;
  updated_at: string;
  type?: 'anime' | 'game' | 'book';
}
```

**加载状态**:
```typescript
export type LoadingState = 'idle' | 'loading' | 'success' | 'error';
```

**核心功能**:

1. **搜索功能**: 按标题实时过滤
2. **类别筛选器**:
   - 类型筛选器: 全部、动画、游戏、书籍
   - 状态筛选器: 已追完、在看、在玩、已通关
3. **响应式网格**: 根据屏幕大小从 2 列自适应到 6 列
4. **图片优化**: 使用 Next.js Image 和懒加载(前 6 项使用 eager)
5. **悬停效果**: 悬停时的缩放和亮度过渡
6. **错误处理**: 失败数据获取的重试机制
7. **空状态**: 无结果与无收藏的不同消息

**筛选逻辑**:
```typescript
const filteredItems = useMemo(() => {
  return items.filter(item => {
    const matchesSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFilter = activeFilter === '全部' ||
      item.status === activeFilter ||
      (activeFilter === '动画' && item.type === 'anime') ||
      (activeFilter === '游戏' && item.type === 'game') ||
      (activeFilter === '书籍' && item.type === 'book');
    return matchesSearch && matchesFilter;
  });
}, [items, searchQuery, activeFilter]);
```

### 聊天组件

#### 消息气泡 ([`MessageBubble.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/MessageBubble.tsx))

显示聊天消息,支持:

**功能**:
- 用户和助手消息区分
- 打字效果支持(通过 `currentContent` prop)
- 带重试按钮的错误状态显示
- 附件的上下文数据解析
- 时间戳显示

**上下文解析**:
```typescript
const parseContext = (text: string): { context: ContextData | null; cleanedContent: string } => {
  if (text.startsWith('[Context: ')) {
    const contextRegex = /\[Context: (\{[^\]]+\})\]/;
    const match = text.match(contextRegex);

    if (match && match[1]) {
      try {
        const contextData = JSON.parse(match[1]) as ContextData;
        const cleanedContent = text.replace(contextRegex, '').trim();
        return { context: contextData, cleanedContent };
      } catch (error) {
        console.error('Failed to parse context:', error);
        return { context: null, cleanedContent: text };
      }
    }
  }

  return { context: null, cleanedContent: text };
};
```

**样式**:
- 用户消息: 橙色背景(`bg-bg-bubble-user`)
- 助手消息: 浅灰色背景(`bg-bg-bubble-assistant`)
- 错误消息: 带边框的红色背景

#### 聊天输入 ([`ChatInput.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ChatInput.tsx))

用于发送消息的输入组件,具有:

**功能**:
- 带自动调整大小的文本输入
- 带加载状态的发送按钮
- 键盘快捷键(Enter 发送,Shift+Enter 换行)
- 字符计数显示
- 无障碍属性

#### 空状态 ([`EmptyState.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/EmptyState.tsx))

当没有收藏同步时显示:

**内容**:
- 带应用图标的欢迎消息
- 同步收藏的行动号召
- 入门说明

### UI 组件

`components/ui/` 目录包含使用 Tailwind CSS 和主题变量构建的可重用 UI 组件:

**可用组件**:
- [`Button.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Button.tsx): 带变体的按钮(default、outline、ghost)
- [`Input.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Input.tsx): 带图标支持的文本输入
- [`Card.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Card.tsx): 带阴影的卡片容器
- [`Badge.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Badge.tsx): 带变体的徽章组件
- [`Dialog.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Dialog.tsx): 模态对话框组件
- [`Select.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Select.tsx): 下拉选择组件
- [`Switch.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Switch.tsx): 切换开关组件
- [`Checkbox.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Checkbox.tsx): 复选框组件
- [`Label.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Label.tsx): 表单标签组件
- [`Textarea.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Textarea.tsx): 多行文本输入
- [`Tabs.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Tabs.tsx): 选项卡导航组件
- [`Toast.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/Toast.tsx): Toast 通知组件
- [`ThemeSwitcher.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/ThemeSwitcher.tsx): 主题选择组件
- [`PosterCard.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/PosterCard.tsx): 海报显示卡片
- [`SortDropdown.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/SortDropdown.tsx): 排序下拉菜单
- [`NavPillSkeleton.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/ui/NavPillSkeleton.tsx): 骨架屏加载状态

**设计模式**: 所有 UI 组件使用主题变量而非硬编码颜色以保持一致性:
```css
background: var(--background);
color: var(--foreground);
background: var(--primary);
```

---

## API 层

### API 客户端 ([`api.ts`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/lib/api.ts))

API 层基于 Axios 构建,具有集中式配置:

**基础配置**:
```typescript
const api = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});
```

### 核心 API 函数

#### 仪表板统计
```typescript
export async function fetchDashboardStats(): Promise<DashboardStats>
```
获取仪表板统计信息,包括总主题数、收藏数、系统状态和最近活动。

#### 用户同步
```typescript
export async function syncUser(username: string, subjectType?: number): Promise<void>
```
与 Bangumi API 同步用户数据。对于大型同步操作具有 5 分钟超时。

#### 收藏计数
```typescript
export async function getUserCollectionCount(username: string, subjectType: number): Promise<number>
```
获取特定主题类型的收藏计数:
- 类型 1: 书籍
- 类型 2: 动画
- 类型 4: 游戏
- 类型 6: 电影

#### 搜索函数

**Bangumi 搜索**:
```typescript
export async function searchBangumiSubjects(keyword?: string, type?: number): Promise<Subject[]>
```
在 Bangumi 数据库中搜索主题。

**本地搜索**:
```typescript
export async function searchSubjects(keyword?: string, type?: number): Promise<Subject[]>
```
在本地数据库中搜索主题。

**混合搜索**:
```typescript
export async function searchMixedSubjects(keyword?: string, type?: number, username?: string): Promise<Subject[]>
```
同时搜索 Bangumi 和本地数据库,合并结果。

#### 用户收藏
```typescript
export async function getUserCollections(username: string, keyword?: string, type?: number): Promise<CollectionWithSubject[]>
```
获取用户的收藏,可选按关键词和类型过滤。

#### 数据导入

**豆瓣导入**:
```typescript
export async function uploadDoubanFile(file: File, username: string): Promise<{ message: string; username: string; import_count: number }>
```
从豆瓣 CSV 文件导入收藏。使用 FormData 进行文件上传,具有 5 分钟超时。

**批量导入**:
```typescript
export async function batchImportCollections(items: ImportItem[], username: string): Promise<{ message: string; imported_count: number }>
```
在单个请求中导入多个收藏。

**手动添加**:
```typescript
export async function createManualCollection(data: ManualCollectionData, username: string): Promise<{ message: string; subject_id: number; collection_id: number }>
```
手动创建带有主题详细信息的收藏。

#### 用户管理

**获取 Bangumi 用户**:
```typescript
export async function fetchBangumiUser(username: string): Promise<BangumiUser | null>
```
直接从 Bangumi API 获取用户信息。

**注册本地用户**:
```typescript
export async function registerLocalUser(data: LocalUserRegisterRequest): Promise<LocalUserRegisterResponse>
```
在数据库中注册本地用户。

**检查本地用户**:
```typescript
export async function checkLocalUser(username: string): Promise<LocalUserCheckResponse>
```
检查用户是否存在于本地数据库中。

**获取用户信息**:
```typescript
export async function getUserInfo(username: string): Promise<BangumiUser | null>
```
从本地数据库获取用户信息。

### 类型定义

**主题接口**:
```typescript
export interface Subject {
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
  rating_details: Record<string, number | string>;
  images: Record<string, string>;
  is_collected?: boolean;
  collection_info?: CollectionInfo;
}
```

**收藏接口**:
```typescript
export interface Collection {
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
```

**BangumiUser 接口**:
```typescript
export interface BangumiUser {
  id: number;
  username: string;
  nickname: string;
  sign: string;
  bangumi_id?: string;
  avatar: {
    large: string;
    medium: string;
    small: string;
  };
}
```

### API 路由代理

应用包含一个 API 路由代理,位于 [`app/api/collections/route.ts`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/api/collections/route.ts):

**目的**: 代理请求到后端 API 以避免 CORS 问题并添加额外的验证。

**实现**:
```typescript
export async function GET(request: Request) {
  try {
    const searchParams = new URL(request.url).searchParams;
    const backendUrl = new URL(`${BACKEND_URL}/api/v1/collections/`);

    // 转发所有查询参数
    searchParams.forEach((value, key) => {
      backendUrl.searchParams.append(key, value);
    });

    // 验证用户名
    if (!backendUrl.searchParams.has('username')) {
      return NextResponse.json({ error: 'Username is required' }, { status: 400 });
    }

    const response = await fetch(backendUrl.toString());

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Backend API error: ${response.status}`);
    }

    const collections = await response.json();
    return NextResponse.json(collections);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to fetch collections' }, { status: 500 });
  }
}
```

---

## 状态管理

应用采用混合方法进行状态管理:

### React Context API

用于需要在多个组件之间共享的全局应用状态。

#### SettingsContext ([`SettingsContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/SettingsContext.tsx))

管理用户设置和认证状态。

**接口定义**:
```typescript
interface SettingsContextType {
  settings: Settings;
  userInfo: BangumiUser | null;
  isRemembered: boolean;
  updateSettings: (newSettings: Partial<Settings>, remember: boolean) => void;
  resetSession: () => void;
  refreshUserInfo: (username: string) => Promise<void>;
  setUserInfo: (userInfo: BangumiUser | null) => void;
}
```

**核心功能**:
- 用户信息存储和检索
- 设置持久化到 localStorage
- 会话管理(记住我功能)
- 用户信息刷新

**实现细节**:
```typescript
export const SettingsProvider = ({ children }: { children: ReactNode }) => {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [userInfo, setUserInfo] = useState<BangumiUser | null>(null);
  const [isRemembered, setIsRemembered] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const sessionTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 从 localStorage 加载设置
  useEffect(() => {
    const loadSettings = () => {
      try {
        const savedSettings = localStorage.getItem('otakuneko_settings');
        const savedUserInfo = localStorage.getItem('otakuneko_userInfo');
        const savedIsRemembered = localStorage.getItem('otakuneko_isRemembered');

        if (savedSettings) {
          setSettings(JSON.parse(savedSettings));
        }
        if (savedUserInfo) {
          setUserInfo(JSON.parse(savedUserInfo));
        }
        if (savedIsRemembered) {
          setIsRemembered(JSON.parse(savedIsRemembered));
        }
      } catch (error) {
        console.error('Failed to load settings:', error);
      } finally {
        setIsInitialized(true);
      }
    };

    loadSettings();
  }, []);

  // 更新设置
  const updateSettings = (newSettings: Partial<Settings>, remember: boolean) => {
    setSettings(prev => {
      const updated = { ...prev, ...newSettings };
      if (remember) {
        localStorage.setItem('otakuneko_settings', JSON.stringify(updated));
      }
      return updated;
    });
    setIsRemembered(remember);
    localStorage.setItem('otakuneko_isRemembered', JSON.stringify(remember));
  };

  // 重置会话
  const resetSession = () => {
    setUserInfo(null);
    localStorage.removeItem('otakuneko_userInfo');
    if (sessionTimerRef.current) {
      clearTimeout(sessionTimerRef.current);
      sessionTimerRef.current = null;
    }
  };

  // 刷新用户信息
  const refreshUserInfo = async (username: string) => {
    try {
      const updatedUserInfo = await getUserInfo(username);
      if (updatedUserInfo) {
        setUserInfo(updatedUserInfo);
        localStorage.setItem('otakuneko_userInfo', JSON.stringify(updatedUserInfo));
      }
    } catch (error) {
      console.error('Failed to refresh user info:', error);
    }
  };

  return (
    <SettingsContext.Provider
      value={{
        settings,
        userInfo,
        isRemembered,
        updateSettings,
        resetSession,
        refreshUserInfo,
        setUserInfo,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
};
```

#### ChatContext ([`ChatContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/ChatContext.tsx))

管理聊天相关的状态。

**接口定义**:
```typescript
interface ChatContextType {
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  removeMessage: (id: string) => void;
  clearMessages: () => void;
  referenceItems: Subject[];
  setReferenceItems: (items: Subject[]) => void;
}
```

**核心功能**:
- 消息列表管理
- 添加、更新、删除消息
- 参考项存储(用于上下文)
- 消息清除

#### HeaderContext ([`HeaderContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/HeaderContext.tsx))

管理 Header 组件的状态,确保在页面转换间保持持久。

**接口定义**:
```typescript
interface HeaderContextType {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  searchResults: Subject[];
  setSearchResults: (results: Subject[]) => void;
  isSearchDropdownOpen: boolean;
  setIsSearchDropdownOpen: (open: boolean) => void;
  isSearching: boolean;
  setIsSearching: (searching: boolean) => void;
  isPopoverOpen: boolean;
  setIsPopoverOpen: (open: boolean) => void;
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  isGridImportOpen: boolean;
  setIsGridImportOpen: (open: boolean) => void;
  clearSearch: () => void;
}
```

**核心功能**:
- 搜索查询和结果管理
- 搜索下拉状态
- 各种模态框状态(设置、网格导入等)
- 搜索清除功能

### Zustand Store

用于复杂状态管理,特别是同步功能。

#### SyncStore ([`syncStore.ts`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/lib/syncStore.ts))

使用 Zustand 管理同步状态和收藏计数。

**状态接口**:
```typescript
interface SyncState {
  isSyncing: boolean;
  isLoading: boolean;
  collectionCounts: {
    anime: number;
    books: number;
    games: number;
    films: number;
  };
  lastSyncTime: Date | null;
  syncError: string | null;

  // Actions
  setSyncing: (syncing: boolean) => void;
  setLoading: (loading: boolean) => void;
  setCollectionCounts: (counts: CollectionCounts) => void;
  setLastSyncTime: (time: Date | null) => void;
  setSyncError: (error: string | null) => void;
  fetchCollectionCounts: (username: string) => Promise<void>;
  performSync: (username: string) => Promise<void>;
}
```

**核心功能**:
- 同步状态跟踪(同步中、加载中、错误)
- 收藏计数管理
- 最后同步时间跟踪
- 收藏计数获取
- 同步执行

**实现示例**:
```typescript
export const useSyncStore = create<SyncState>((set, get) => ({
  isSyncing: false,
  isLoading: true,
  collectionCounts: {
    anime: 0,
    books: 0,
    games: 0,
    films: 0
  },
  lastSyncTime: null,
  syncError: null,

  setSyncing: (syncing) => set({ isSyncing: syncing }),
  setLoading: (loading) => set({ isLoading: loading }),
  setCollectionCounts: (counts) => set({ collectionCounts: counts }),
  setLastSyncTime: (time) => set({ lastSyncTime: time }),
  setSyncError: (error) => set({ syncError: error }),

  fetchCollectionCounts: async (username: string) => {
    set({ isLoading: true, syncError: null });
    try {
      const [animeCount, booksCount, gamesCount, filmsCount] = await Promise.all([
        getUserCollectionCount(username, 2),
        getUserCollectionCount(username, 1),
        getUserCollectionCount(username, 4),
        getUserCollectionCount(username, 6),
      ]);

      set({
        collectionCounts: {
          anime: animeCount,
          books: booksCount,
          games: gamesCount,
          films: filmsCount,
        },
        isLoading: false,
      });
    } catch (error) {
      set({
        syncError: 'Failed to fetch collection counts',
        isLoading: false,
      });
    }
  },

  performSync: async (username: string) => {
    set({ isSyncing: true, syncError: null });
    try {
      await syncUser(username);
      await get().fetchCollectionCounts(username);
      set({
        isSyncing: false,
        lastSyncTime: new Date(),
      });
    } catch (error) {
      set({
        syncError: 'Failed to sync data',
        isSyncing: false,
      });
    }
  },
}));
```

---

## 样式系统

### 主题变量

应用使用 CSS 自定义属性实现主题系统,定义在 [`globals.css`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/app/globals.css) 中。

**主题结构**:
```css
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --card: 0 0% 100%;
  --card-foreground: 222.2 84% 4.9%;
  --popover: 0 0% 100%;
  --popover-foreground: 222.2 84% 4.9%;
  --primary: 222.2 47.4% 11.2%;
  --primary-foreground: 210 40% 98%;
  --secondary: 210 40% 96.1%;
  --secondary-foreground: 222.2 47.4% 11.2%;
  --muted: 210 40% 96.1%;
  --muted-foreground: 215.4 16.3% 46.9%;
  --accent: 210 40% 96.1%;
  --accent-foreground: 222.2 47.4% 11.2%;
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 210 40% 98%;
  --border: 214.3 31.8% 91.4%;
  --input: 214.3 31.8% 91.4%;
  --ring: 222.2 84% 4.9%;
  --radius: 0.5rem;

  /* 特定主题颜色 */
  --bg-bubble-user: 249.6 89.6% 63.2%;
  --bg-bubble-assistant: 210 40% 96.1%;
  --bg-sidebar: 0 0% 96.1%;
  --bg-header: 0 0% 100%;
}
```

### 主题变体

应用支持三种主题变体:

#### Default Theme
- 背景色: 白色
- 前景色: 深灰
- 主色调: 深蓝灰
- 适合: 通用使用

#### Ocean Theme
- 背景色: 浅蓝
- 前景色: 深蓝
- 主色调: 海洋蓝
- 适合: 冷色调偏好

#### Sakura Theme
- 背景色: 浅粉
- 前景色: 深粉
- 主色调: 樱花粉
- 适合: 暖色调偏好

### Tailwind CSS 配置

应用使用 Tailwind CSS 进行样式设计,配置为使用主题变量:

**主题映射**:
```javascript
theme: {
  extend: {
    colors: {
      background: 'hsl(var(--background))',
      foreground: 'hsl(var(--foreground))',
      card: 'hsl(var(--card))',
      'card-foreground': 'hsl(var(--card-foreground))',
      popover: 'hsl(var(--popover))',
      'popover-foreground': 'hsl(var(--popover-foreground))',
      primary: 'hsl(var(--primary))',
      'primary-foreground': 'hsl(var(--primary-foreground))',
      secondary: 'hsl(var(--secondary))',
      'secondary-foreground': 'hsl(var(--secondary-foreground))',
      muted: 'hsl(var(--muted))',
      'muted-foreground': 'hsl(var(--muted-foreground))',
      accent: 'hsl(var(--accent))',
      'accent-foreground': 'hsl(var(--accent-foreground))',
      destructive: 'hsl(var(--destructive))',
      'destructive-foreground': 'hsl(var(--destructive-foreground))',
      border: 'hsl(var(--border))',
      input: 'hsl(var(--input))',
      ring: 'hsl(var(--ring))',
    },
  },
}
```

### 响应式设计

应用采用移动优先的响应式设计方法:

**断点**:
- `sm`: 640px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px
- `2xl`: 1536px

**响应式示例**:
```tsx
<div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
  {/* 收藏项 */}
</div>
```

### 动画和过渡

应用使用 CSS 过渡和动画增强用户体验:

**常用过渡**:
```css
transition-all duration-200 ease-in-out
transition-colors duration-200
transition-transform duration-200
```

**动画示例**:
```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

---

## 上下文提供者

### 提供者层次结构

应用使用多个上下文提供者来管理全局状态。提供者的顺序至关重要,因为某些提供者依赖于其他提供者的状态。

**提供者层次结构**:
```tsx
<SettingsProvider>
  <ToastProvider>
    <ChatProvider>
      <HeaderProvider>
        <Header />
        <main>{children}</main>
      </HeaderProvider>
    </ChatProvider>
  </ToastProvider>
</SettingsProvider>
```

### SettingsProvider

**位置**: [`contexts/SettingsContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/SettingsContext.tsx)

**职责**:
- 管理用户设置
- 存储和检索用户信息
- 处理会话持久化
- 提供设置更新方法

**使用示例**:
```tsx
const { settings, userInfo, updateSettings, resetSession } = useSettings();

// 更新设置
updateSettings({ theme: 'ocean' }, true);

// 重置会话
resetSession();
```

### ToastProvider

**位置**: [`contexts/ToastContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/ToastContext.tsx)

**职责**:
- 管理 Toast 通知
- 控制通知显示和隐藏
- 管理通知队列

**使用示例**:
```tsx
const { toast } = useToast();

// 显示成功通知
toast({
  title: 'Success',
  description: 'Data saved successfully',
  variant: 'default',
});

// 显示错误通知
toast({
  title: 'Error',
  description: 'Failed to save data',
  variant: 'destructive',
});
```

### ChatProvider

**位置**: [`contexts/ChatContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/ChatContext.tsx)

**职责**:
- 管理聊天消息
- 存储参考项
- 提供消息操作方法

**使用示例**:
```tsx
const { messages, addMessage, setReferenceItems } = useChatContext();

// 添加消息
addMessage({
  id: generateId(),
  role: 'user',
  content: 'Hello',
  currentContent: 'Hello',
  status: 'sent',
  timestamp: new Date().toISOString(),
});

// 设置参考项
setReferenceItems([subject1, subject2]);
```

### HeaderProvider

**位置**: [`contexts/HeaderContext.tsx`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/contexts/HeaderContext.tsx)

**职责**:
- 管理 Header 状态
- 控制搜索功能
- 管理模态框状态

**使用示例**:
```tsx
const {
  searchQuery,
  setSearchQuery,
  isSearchDropdownOpen,
  setIsSearchDropdownOpen,
  clearSearch,
} = useHeaderContext();

// 设置搜索查询
setSearchQuery('anime');

// 打开搜索下拉
setIsSearchDropdownOpen(true);

// 清除搜索
clearSearch();
```

---

## 自定义 Hooks

### useDebounce

**位置**: [`hooks/useDebounce.ts`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useDebounce.ts)

**用途**: 防抖函数调用,减少频繁更新。

**签名**:
```typescript
function useDebounce<T>(value: T, delay: number): T
```

**使用示例**:
```tsx
const [searchQuery, setSearchQuery] = useState('');
const debouncedQuery = useDebounce(searchQuery, 300);

// 使用防抖后的查询进行搜索
useEffect(() => {
  if (debouncedQuery) {
    performSearch(debouncedQuery);
  }
}, [debouncedQuery]);
```

**实现**:
```typescript
import { useState, useEffect } from 'react';

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}
```

### useSync

**位置**: [`hooks/useSync.ts`](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useSync.ts)

**用途**: 封装同步功能,提供简化的同步操作接口。

**返回值**:
```typescript
interface UseSyncReturn {
  isSyncing: boolean;
  isLoading: boolean;
  collectionCounts: CollectionCounts;
  lastSyncTime: Date | null;
  syncError: string | null;
  handleSync: () => Promise<void>;
}
```

**使用示例**:
```tsx
const {
  isSyncing,
  isLoading,
  collectionCounts,
  lastSyncTime,
  handleSync,
} = useSync();

// 触发同步
await handleSync();

// 显示同步状态
{isSyncing && <p>Syncing...</p>}
{isLoading && <p>Loading...</p>}
```

**实现**:
```typescript
import { useEffect } from 'react';
import { useSyncStore } from '@/lib/syncStore';
import { useSettings } from '@/contexts/SettingsContext';

export function useSync() {
  const { settings } = useSettings();
  const {
    isSyncing,
    isLoading,
    collectionCounts,
    lastSyncTime,
    syncError,
    fetchCollectionCounts,
    performSync,
  } = useSyncStore();

  // 在挂载时获取收藏计数
  useEffect(() => {
    if (settings.username) {
      fetchCollectionCounts(settings.username);
    }
  }, [settings.username, fetchCollectionCounts]);

  const handleSync = async () => {
    if (settings.username) {
      await performSync(settings.username);
    }
  };

  return {
    isSyncing,
    isLoading,
    collectionCounts,
    lastSyncTime,
    syncError,
    handleSync,
  };
}
```

---

## 设计模式

### 组件组合模式

应用使用组件组合模式来构建复杂的 UI:

**示例**:
```tsx
<Card>
  <CardHeader>
    <CardTitle>Collection Grid</CardTitle>
    <CardDescription>Manage your anime collection</CardDescription>
  </CardHeader>
  <CardContent>
    <PosterCard
      title="Anime Title"
      posterUrl="/poster.jpg"
      rating={8.5}
      status="Watching"
    />
  </CardContent>
  <CardFooter>
    <Button>View Details</Button>
  </CardFooter>
</Card>
```

### 容器/展示组件模式

应用将容器组件(业务逻辑)与展示组件(UI)分离:

**容器组件**:
```tsx
export function CollectionGridPage() {
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchItems().then(data => {
      setItems(data);
      setIsLoading(false);
    });
  }, []);

  return <CollectionGrid items={items} isLoading={isLoading} />;
}
```

**展示组件**:
```tsx
export function CollectionGrid({ items, isLoading }: CollectionGridProps) {
  if (isLoading) {
    return <LoadingSpinner />;
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {items.map(item => (
        <PosterCard key={item.id} {...item} />
      ))}
    </div>
  );
}
```

### 自定义 Hook 模式

应用使用自定义 hooks 来封装可重用的逻辑:

**示例**:
```tsx
// Hook 定义
export function useCollectionFilters() {
  const [activeFilter, setActiveFilter] = useState('全部');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredItems = useMemo(() => {
    return items.filter(item => {
      const matchesSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesFilter = activeFilter === '全部' || item.status === activeFilter;
      return matchesSearch && matchesFilter;
    });
  }, [items, searchQuery, activeFilter]);

  return { activeFilter, setActiveFilter, searchQuery, setSearchQuery, filteredItems };
}

// Hook 使用
function CollectionPage() {
  const { activeFilter, setActiveFilter, searchQuery, setSearchQuery, filteredItems } = useCollectionFilters();

  return (
    <>
      <SearchInput value={searchQuery} onChange={setSearchQuery} />
      <FilterTabs activeFilter={activeFilter} onChange={setActiveFilter} />
      <CollectionGrid items={filteredItems} />
    </>
  );
}
```

### 状态提升模式

应用将状态提升到最近的共同祖先组件以共享状态:

**示例**:
```tsx
// 父组件
export function ParentComponent() {
  const [sharedState, setSharedState] = useState('initial');

  return (
    <>
      <ChildA value={sharedState} onChange={setSharedState} />
      <ChildB value={sharedState} />
    </>
  );
}

// 子组件
export function ChildA({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input value={value} onChange={e => onChange(e.target.value)} />;
}

export function ChildB({ value }: { value: string }) {
  return <p>Shared value: {value}</p>;
}
```

### 受控组件模式

应用使用受控组件模式来管理表单输入:

**示例**:
```tsx
export function ControlledInput() {
  const [value, setValue] = useState('');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue(e.target.value);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    console.log('Submitted:', value);
  };

  return (
    <form onSubmit={handleSubmit}>
      <Input
        value={value}
        onChange={handleChange}
        placeholder="Enter text..."
      />
      <Button type="submit">Submit</Button>
    </form>
  );
}
```

---

## 最佳实践

### 代码组织

1. **按功能组织组件**: 将相关组件放在同一目录中
2. **使用清晰的命名**: 组件和函数名称应描述其用途
3. **保持组件小巧**: 每个组件应专注于单一职责
4. **使用类型定义**: 为所有 props、状态和函数参数定义 TypeScript 类型

### 性能优化

1. **使用 useMemo 缓存计算结果**:
```tsx
const filteredItems = useMemo(() => {
  return items.filter(item => item.status === activeFilter);
}, [items, activeFilter]);
```

2. **使用 useCallback 缓存函数**:
```tsx
const handleClick = useCallback(() => {
  console.log('Clicked');
}, []);
```

3. **使用 React.lazy 进行代码分割**:
```tsx
const LazyComponent = React.lazy(() => import('./LazyComponent'));
```

4. **使用 Next.js Image 进行图片优化**:
```tsx
<Image
  src="/poster.jpg"
  alt="Poster"
  width={200}
  height={300}
  loading="lazy"
/>
```

5. **避免不必要的重新渲染**:
```tsx
const MemoizedComponent = React.memo(({ data }) => {
  return <div>{data}</div>;
});
```

### 无障碍性

1. **使用语义化 HTML**:
```tsx
<nav aria-label="Main navigation">
  <ul>
    <li><a href="/">Home</a></li>
    <li><a href="/collections">Collections</a></li>
  </ul>
</nav>
```

2. **添加 ARIA 属性**:
```tsx
<button
  aria-label="Close dialog"
  onClick={onClose}
>
  <X />
</button>
```

3. **键盘导航支持**:
```tsx
<div
  role="button"
  tabIndex={0}
  onKeyDown={handleKeyDown}
  onClick={handleClick}
>
  Clickable element
</div>
```

4. **提供替代文本**:
```tsx
<Image
  src="/poster.jpg"
  alt="Anime poster showing main character"
  width={200}
  height={300}
/>
```

### 错误处理

1. **使用 try-catch 处理异步错误**:
```tsx
const fetchData = async () => {
  try {
    const response = await api.get('/data');
    setData(response.data);
  } catch (error) {
    console.error('Failed to fetch data:', error);
    setError('Failed to load data');
  }
};
```

2. **使用错误边界捕获组件错误**:
```tsx
class ErrorBoundary extends React.Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return <div>Something went wrong</div>;
    }
    return this.props.children;
  }
}
```

3. **提供有意义的错误消息**:
```tsx
toast({
  title: 'Sync Failed',
  description: 'Unable to sync with Bangumi. Please check your connection and try again.',
  variant: 'destructive',
});
```

### 测试

1. **编写单元测试**:
```tsx
import { render, screen } from '@testing-library/react';
import { Button } from './Button';

test('renders button with text', () => {
  render(<Button>Click me</Button>);
  expect(screen.getByText('Click me')).toBeInTheDocument();
});
```

2. **编写集成测试**:
```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInput } from './ChatInput';

test('submits message on enter', () => {
  const handleSubmit = jest.fn();
  render(<ChatInput onSubmit={handleSubmit} />);

  const input = screen.getByPlaceholderText('Type a message...');
  fireEvent.change(input, { target: { value: 'Hello' } });
  fireEvent.keyDown(input, { key: 'Enter' });

  expect(handleSubmit).toHaveBeenCalledWith('Hello');
});
```

3. **使用测试工具**:
```tsx
import { renderHook, act } from '@testing-library/react';
import { useDebounce } from './useDebounce';

test('debounces value changes', () => {
  jest.useFakeTimers();
  const { result, rerender } = renderHook(
    ({ value, delay }) => useDebounce(value, delay),
    { initialProps: { value: 'initial', delay: 500 } }
  );

  expect(result.current).toBe('initial');

  rerender({ value: 'updated', delay: 500 });
  expect(result.current).toBe('initial');

  act(() => {
    jest.advanceTimersByTime(500);
  });

  expect(result.current).toBe('updated');
  jest.useRealTimers();
});
```

### 安全性

1. **验证用户输入**:
```tsx
const validateUsername = (username: string): boolean => {
  const usernameRegex = /^[a-zA-Z0-9_-]{3,20}$/;
  return usernameRegex.test(username);
};
```

2. **清理用户输入**:
```tsx
import DOMPurify from 'dompurify';

const sanitizeInput = (input: string): string => {
  return DOMPurify.sanitize(input);
};
```

3. **使用 HTTPS**:
```tsx
const api = axios.create({
  baseURL: 'https://api.example.com',
  // ...
});
```

4. **避免暴露敏感信息**:
```tsx
// 错误: 不要记录敏感信息
console.error('Login failed:', { password: userPassword });

// 正确: 只记录必要信息
console.error('Login failed:', { username: userUsername });
```

### 文档

1. **为组件编写 JSDoc 注释**:
```tsx
/**
 * CollectionGrid component displays a grid of collection items
 * @param {CollectionItem[]} items - Array of collection items to display
 * @param {(item: CollectionItem) => void} onItemClick - Callback when an item is clicked
 * @param {string} className - Additional CSS classes
 */
export function CollectionGrid({
  items,
  onItemClick,
  className,
}: CollectionGridProps) {
  // ...
}
```

2. **为函数编写注释**:
```tsx
/**
 * Filters items based on search query and active filter
 * @param {CollectionItem[]} items - Items to filter
 * @param {string} searchQuery - Search query string
 * @param {string} activeFilter - Active filter value
 * @returns {CollectionItem[]} Filtered items
 */
export function filterItems(
  items: CollectionItem[],
  searchQuery: string,
  activeFilter: string
): CollectionItem[] {
  // ...
}
```

3. **维护 README 文件**:
```markdown
# OtakuNeko Frontend

## Installation
npm install

## Development
npm run dev

## Build
npm run build

## Testing
npm test
```

---

## 总结

OtakuNeko 前端是一个功能丰富、架构良好的应用,展示了现代 React 和 Next.js 开发的最佳实践。通过使用 TypeScript、Context API、Zustand、Tailwind CSS 和其他工具,应用提供了类型安全、高性能和可维护的代码库。

关键特性包括:
- 响应式设计和移动优先方法
- 全面的主题系统
- 高效的状态管理
- 清晰的代码组织
- 强大的 API 集成
- 优秀的用户体验

通过遵循本文档中概述的设计模式和最佳实践,开发者可以有效地理解和扩展 OtakuNeko 前端代码库。
