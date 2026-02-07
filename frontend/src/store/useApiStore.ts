import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// --- 1. 定义配置结构 ---

export interface ProviderConfig {
  enabled: boolean;
  apiKey: string;
  endpoint?: string;      // 大多数兼容 OpenAI 协议的服务商都需要这个
  proxyUrl?: string;      // 专门为 OpenAI 设计的代理地址
  deploymentName?: string;// 专门为 Azure 设计的模型部署名
  apiVersion?: string;    // 专门为 Azure 设计的 API 版本
}

interface ApiStoreState {
  // 存储所有服务商的配置
  config: {
    // === 国际主流 ===
    openai: ProviderConfig;
    azure: ProviderConfig;
    google: ProviderConfig;    // Gemini
    anthropic: ProviderConfig; // Claude
    
    // === 国产模型 (全部支持 OpenAI 兼容协议) ===
    deepseek: ProviderConfig;  // 深度求索
    moonshot: ProviderConfig;  // Kimi / 月之暗面
    qwen: ProviderConfig;      // 通义千问 (阿里云 DashScope)
    zhipu: ProviderConfig;     // 智谱 GLM (BigModel)
    minimax: ProviderConfig;   // 海螺 (MiniMax)
    yi: ProviderConfig;        // 零一万物 (01.AI)
    stepfun: ProviderConfig;   // 阶跃星辰
    
    // === 其他 & 本地 ===
    ollama: ProviderConfig;    // 本地模型
    groq: ProviderConfig;      // 极速推理
    perplexity: ProviderConfig;// 联网搜索模型
    mistral: ProviderConfig;   // 法国开源之光
  };

  // 动作
  setProviderConfig: (provider: keyof ApiStoreState['config'], field: keyof ProviderConfig, value: any) => void;
  getProviderConfig: (provider: keyof ApiStoreState['config']) => ProviderConfig;
  clearAllKeys: () => void;
}

// --- 2. 默认配置 (包含官方 Endpoints) ---

const initialConfig: ApiStoreState['config'] = {
  // === 国际 ===
  openai: { 
    enabled: true, 
    apiKey: '', 
    proxyUrl: '' // 留空则使用官方 https://api.openai.com/v1
  },
  azure: { 
    enabled: false, 
    apiKey: '', 
    endpoint: '', // 格式通常为 https://{resource-name}.openai.azure.com
    deploymentName: '', 
    apiVersion: '2024-02-15-preview' 
  },
  google: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://generativelanguage.googleapis.com/v1beta/openai/' // Gemini 的 OpenAI 兼容地址
  },
  anthropic: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.anthropic.com' 
  },

  // === 国产 (Endpoint 均为官方兼容接口) ===
  deepseek: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.deepseek.com' 
  },
  moonshot: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.moonshot.cn/v1' 
  },
  qwen: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://dashscope.aliyuncs.com/compatible-mode/v1' 
  },
  zhipu: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://open.bigmodel.cn/api/paas/v4' 
  },
  minimax: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.minimax.chat/v1' 
  },
  yi: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.lingyiwanwu.com/v1' 
  },
  stepfun: {
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.stepfun.com/v1' 
  },

  // === 其他 ===
  ollama: { 
    enabled: false, 
    apiKey: 'ollama', // Ollama 通常不需要 Key，但某些客户端库可能需要非空值
    endpoint: 'http://localhost:11434/v1' // 注意：加上 /v1 以适配 OpenAI SDK
  },
  groq: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.groq.com/openai/v1' 
  },
  perplexity: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.perplexity.ai' 
  },
  mistral: { 
    enabled: false, 
    apiKey: '', 
    endpoint: 'https://api.mistral.ai/v1' 
  },
};

// --- 3. 创建 Store ---

export const useApiStore = create<ApiStoreState>()(
  persist(
    (set, get) => ({
      config: initialConfig,

      setProviderConfig: (provider, field, value) =>
        set((state) => ({
          config: {
            ...state.config,
            [provider]: {
              ...state.config[provider],
              [field]: value,
            },
          },
        })),

      getProviderConfig: (provider) => {
        return get().config[provider];
      },

      clearAllKeys: () => {
        set({ config: initialConfig });
      }
    }),
    {
      name: 'lobe-api-keys-storage', // LocalStorage 中的 Key 名称
      storage: createJSONStorage(() => localStorage),
      version: 1, // 版本控制，方便后续迁移数据
    }
  )
);