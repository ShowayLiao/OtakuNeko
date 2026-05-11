# Timetable 页面性能优化计划

> **目标**：解决 `frontend/src/app/Timetable/page.tsx` 打开和渲染速度慢的问题
> **日期**：2026-05-11

---

## 一、现状诊断

### 瓶颈概览

| 层级 | 问题 | 严重度 |
|------|------|--------|
| **数据加载** | 首屏 2 个无条件 HTTP 请求串/并行阻塞渲染 | 🔴 高 |
| **数据加载** | CollectionPanel 折叠时仍发起网络请求 | 🔴 高 |
| **计算渲染** | TimelineBoard 拖拽时全量重算 itemsBySlotMap (O(N×7)) | 🔴 高 |
| **计算渲染** | StandardLanes Tetris 布局算法拖拽时全量重算 | 🔴 高 |
| **计算渲染** | 50+ 个 TimelineMediaCard 各自创建 ResizeObserver | 🟡 中 |
| **渲染隔离** | 大量子组件缺少 React.memo，drag state 变化导致全树重渲染 | 🔴 高 |
| **渲染隔离** | 内联匿名函数致子组件 props 不稳定 | 🟡 中 |
| **包体积** | @lobehub/ui + antd 无按需/懒加载 | 🟡 中 |
| **日志输出** | scheduleService 中大量 console.log 阻塞主线程 | 🟡 中 |

---

## 二、Tier 1 优化方案（低成本、高收益、低风险）

### A. TimelineMediaCard 添加 React.memo

**文件**：`frontend/src/components/timetable/TimelineMediaCard.tsx`

**现状**：每次父级 drag/hover state 变化，所有卡片无条件重渲染（含 ResizeObserver 重新初始化）。

**方案**：包裹 `React.memo`，自定义比较函数只对比影响渲染的 props。

### B. DraggableItemWrapper 添加 React.memo

**文件**：`frontend/src/components/timetable/DraggableItemWrapper.tsx`

**现状**：拖拽时所有 DraggableItemWrapper 重渲染，尽管只有被拖拽项需要更新。

**方案**：包裹 `React.memo`，对比 `id` 和 `data.source_id` 等关键字段。

### C. page.tsx 稳定回调引用

**文件**：`frontend/src/app/Timetable/page.tsx`

**现状**：部分回调已用 `useCallback`（如 `handleResize`、`handleDelete`），但存在内联匿名函数。

**方案**：将剩余内联函数提取为 `useCallback` 包裹，确保传给子组件的 props 引用稳定。

### D. CollectionPanel 条件渲染

**文件**：
- `frontend/src/app/Timetable/page.tsx`
- `frontend/src/components/timetable/DraggablePanel.tsx`

**现状**：CollectionPanel 在面板折叠时仍然渲染并发送 HTTP 请求。

**方案**：折叠时不请求数据，或延迟请求至展开时；减少首屏网络竞争。

### E. 生产环境清理 console.log

**文件**：
- `frontend/src/services/scheduleService.ts`
- `frontend/src/components/timetable/DraggablePanel.tsx`

**现状**：数据转换循环中大量 `console.log`，每次数据更新都执行。

**方案**：移除转换循环中的 verbose 日志，仅保留关键错误日志。

---

## 三、后续 Tier 规划

| Tier | 措施 | 预期收益 |
|------|------|----------|
| **Tier 2** | `next/dynamic` 懒加载 CollectionPanel、ExportTickTickModal | 首屏 JS 体积减 ~40% |
| **Tier 2** | `itemsBySlotMap` 归一化预处理拆分 | 避免拖拽时重复归一化 |
| **Tier 2** | TimelineBoard、StandardLanes 包裹 React.memo | 隔离 drag state 影响 |
| **Tier 3** | CSS Container Queries 替代 ResizeObserver | 消除 50+ JS 监听器 |
| **Tier 3** | `useTransition` 隔离拖拽状态更新 | UI 不卡顿 |
| **Tier 3** | 虚拟滚动 | 大列表 DOM 节点减 90% |

---

## 四、验证方式

1. **React DevTools Profiler**：录制页面加载和拖拽操作，对比优化前后的 commit 耗时
2. **Lighthouse / Performance 面板**：检查 FCP（First Contentful Paint）和 TBT（Total Blocking Time）
3. **肉眼感知**：拖拽卡片时是否流畅无卡顿
