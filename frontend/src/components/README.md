# Components 模块

基于 `@lobehub/ui` + `antd 6` 的 UI 组件库，按业务域划分为 6 个子模块。

## 子模块

| 目录 | 功能 | 核心依赖 |
|------|------|----------|
| `chat/` | AI 聊天界面（ChatPage 主组件、ChatInput、ModelSelector、RoleSelector、SearchBar） | `@lobehub/ui/chat`, `zustand` |
| `collection/` | 收藏展示（CollectionContent 列表/网格、MediaCard 卡片、BilibiliIcon） | `antd` |
| `header/` | 各页面顶部工具栏（ChatHeader、CollectionHeader、TimetableHeader、PersonaHeader、User、SearchBar） | `@lobehub/ui`, `lucide-react` |
| `timetable/` | 排班表拖拽系统（TimelineBoard、DraggablePanel、DraggableItemWrapper、DroppableCell、StandardLanes 等） | `@dnd-kit/core`, `@dnd-kit/sortable` |
| `Modal/` | 全局弹窗（LoginModal、ApiKeyModal、SubjectModal、ImportModal、ExportCalendarModal 等 8 个弹窗 + SubjectForm 子表单） | `@lobehub/ui`, `antd` |
| `providers/` | 全局上下文（LobeProvider 主题/外观管理、ColorSchemes 配色常量） | `@lobehub/ui`, `antd` |
| `sidebar/` | 角色侧边栏（RoleSidebar） | `@lobehub/ui` |

## 依赖关系

```
components/
├── 依赖 → services/   (API 调用)
├── 依赖 → store/      (useRoleStore, useApiStore)
├── 依赖 → stores/     (useChatStore)
├── 依赖 → lib/        (fetcher.ts SSE 流式聊天)
└── 依赖 → features/   (Sidebar, Theme 切换)
```

## 设计模式

- **全屏布局**: APPLayout 使用 `position: fixed` + `100vw/100vh`，子页面自行管理 overflow
- **主题**: 通过 `useAppTheme()` 获取 `isDarkMode`，配合 Ant Design `token` 动态取色
- **拖拽**: timetable 子模块基于 `@dnd-kit` 实现可拖拽排班
