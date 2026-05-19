import { useApiStore } from '@/store/useApiStore';

interface PromptConfig {
  persona: string;
  tone: string;
  rules: string;
}

interface ChatWithBackendOptions {
  messages: any[];
  provider: string;
  model?: string;
  temperature?: number;
  prompt_config?: PromptConfig;
  thread_id?: string;
  onMessageChunk?: (chunk: string) => void;
  onToolStart?: (name: string, inputs: any) => void;
  onToolEnd?: (name: string, output: any) => void;
  onError?: (error: string) => void;
  onComplete?: () => void;
}

// 解析 SSE 事件流
const parseSSE = (text: string) => {
  const events = [];
  const lines = text.split('\n');
  let event = { type: 'message', data: '' };
  
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event.type = line.substring(6).trim();
    } else if (line.startsWith('data:')) {
      event.data += line.substring(5).trim() + '\n';
    } else if (line === '') {
      if (event.data) {
        try {
          event.data = JSON.parse(event.data.trim());
        } catch (e) {
          // 忽略解析错误
        }
        events.push({ ...event });
        event = { type: 'message', data: '' };
      }
    }
  }
  
  return events;
};

export const chatWithBackend = async ({
  messages,
  provider,
  model = 'gpt-3.5-turbo',
  temperature = 0.7,
  prompt_config,
  thread_id,
  onMessageChunk,
  onToolStart,
  onToolEnd,
  onError,
  onComplete
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
      prompt_config,
      thread_id,
    }),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    
    // 只要 buffer 中包含完整的 SSE 事件（以双换行符结尾）
    let eventEndIndex;
    while ((eventEndIndex = buffer.indexOf('\n\n')) !== -1) {
      // 1. 截取出一个完整的事件文本进行解析
      const chunkToParse = buffer.slice(0, eventEndIndex + 2);
      
      // 2. 核心修复：从 buffer 中删掉已经截取走的部分！
      buffer = buffer.slice(eventEndIndex + 2);
      
      // 3. 解析这单个完整事件
      const events = parseSSE(chunkToParse);
      
      for (const event of events) {
        switch (event.type) {
          case 'message_chunk':
            if (event.data.content && onMessageChunk) {
              onMessageChunk(event.data.content);
            }
            break;
          case 'tool_start':
            if (event.data.name && onToolStart) {
              onToolStart(event.data.name, event.data.inputs);
            }
            break;
          case 'tool_end':
            if (event.data.name && onToolEnd) {
              onToolEnd(event.data.name, event.data.output);
            }
            break;
          case 'error':
            if (event.data.detail && onError) {
              onError(event.data.detail);
            }
            break;
        }
      }
    }
  }

  if (onComplete) {
    onComplete();
  }
};

export const fetchChatHistory = async (threadId: string): Promise<any[]> => {
  const response = await fetch(
    `http://localhost:8000/api/v1/chat/history?thread_id=${encodeURIComponent(threadId)}`
  );
  if (!response.ok) return [];
  const data = await response.json();
  return data.messages || [];
};
