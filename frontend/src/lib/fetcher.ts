import { useApiStore } from '@/store/useApiStore';

interface ChatWithBackendOptions {
  messages: any[];
  provider: string;
  model?: string;
  temperature?: number;
}

export const chatWithBackend = async ({
  messages,
  provider,
  model = 'gpt-3.5-turbo',
  temperature = 0.7
}: ChatWithBackendOptions) => {
  // 1. 【关键】在发起请求的瞬间，从 Store 拿出 Key
  // 注意：这里使用 getState() 可以避免在组件外读取 Store
  const config = (useApiStore.getState().config as any)[provider];

  if (!config || !config.apiKey) {
    throw new Error(`请先在设置中填写 ${provider} 的 API Key`);
  }

  // 2. 将 Key 放入 Header 发送给你的 Python 后端
  const response = await fetch('http://localhost:8000/api/v1/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // 这里是核心！把 Key 透传过去
      'X-Api-Key': config.apiKey,
      'X-Provider-Endpoint': config.endpoint || '', // 如果需要动态换地址
    },
    body: JSON.stringify({
      messages,
      model,
      temperature,
    }),
  });

  return response;
};
