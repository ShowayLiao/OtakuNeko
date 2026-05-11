# Store / Stores 模块

基于 Zustand 的前端状态管理。

> **注意**: 存在 `store/` 和 `stores/` 两个目录，属于历史遗留。`store/` 存放应用级配置与角色管理，`stores/` 仅含聊天状态。

## store/ — 应用级 Store

| 文件 | Store 名 | 持久化 | 职责 |
|------|----------|--------|------|
| [useApiStore.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/useApiStore.ts) | `useApiStore` | ✅ localStorage | 15+ LLM 服务商 API Key 配置（OpenAI/Azure/DeepSeek/Kimi 等） |
| [useRoleStore.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/useRoleStore.ts) | `useRoleStore` | ✅ localStorage | 自定义 AI 角色 CRUD + 导出/导入 |
| [models.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/models.ts) | — | — | 类型定义（Role, Model, PromptConfig）+ MODEL_LIST 常量 |
| [presetRoles.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/presetRoles.ts) | — | — | 3 个预设角色（漫评分析师/吐槽役/傲娇猫娘） |
| [useHasHydrated.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/store/useHasHydrated.ts) | — | — | SSR 水合完成检测 Hook |

## stores/ — 聊天 Store

| 文件 | Store 名 | 持久化 | 职责 |
|------|----------|--------|------|
| [useChatStore.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/stores/useChatStore.ts) | `useChatStore` | ✅ localStorage | 多会话聊天管理（sessions、chatMessages Map、ToolCall 状态） |

## 架构问题

1. **Map 类型持久化**: `useChatStore` 的 `chatMessages` 为 `Map<string, Message[]>`，Zustand persist 序列化 Map 有兼容性问题，代码中多处加了防御性 `typeof ...get === 'function'` 检查
2. **目录分裂**: `store/` vs `stores/` 两个目录无明确划分标准，建议合并
3. **Store 间无关联**: `useApiStore` 和 `useChatStore` 独立运作，API Key 通过 `getState()` 在 fetcher 中读取，非响应式
