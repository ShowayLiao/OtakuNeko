# Lib 模块

前端工具库，提供 HTTP 通信和通用工具。

| 文件 | 导出 | 职责 |
|------|------|------|
| `fetcher.ts` | `chatWithBackend()` | SSE 流式聊天：从 `useApiStore` 读取 API Key → 透传到后端 `/chat` → 解析 SSE 事件流 |
| `utils.ts` | `cn()` | 类名合并（filter + join），简易版 `clsx` |

## fetcher.ts 工作流

```
ChatPage → chatWithBackend({messages, provider, model, ...})
         → useApiStore.getState().config[provider]  // 非响应式读取 Key
         → fetch('http://localhost:8000/api/v1/chat', {
             headers: { 'X-Api-Key': config.apiKey, ... }
           })
         → SSE stream 解析 → onMessageChunk / onToolStart / onToolEnd
```

## 注意事项

- `chatWithBackend` 使用硬编码 `http://localhost:8000`，未通过 `client.ts` 或环境变量统一管理
- SSE 解析器（`parseSSE`）是自定义实现，未用标准 EventSource API（因为需要 POST + 自定义 Header）
