import { 
  Bot, BrainCircuit, Moon, MessageSquare, Zap, 
  Sparkles, Box, Globe, Cpu, Terminal,
  Cloud, Gauge, Search, 
} from 'lucide-react';

// 定义模型元数据，与 useApiStore.ts 中的 provider key 完全对应
export const MODEL_LIST = [
  // === 国际主流 (International) ===
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai', icon: Bot },
  { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', provider: 'openai', icon: Bot },
  { id: 'claude-3-5-sonnet-latest', name: 'Claude 3.5 Sonnet', provider: 'anthropic', icon: Cloud },
  { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', provider: 'google', icon: Sparkles },
  
  // === 国产大模型 (Chinese Domestic) ===
  { id: 'deepseek-chat', name: 'Chat', provider: 'deepseek', icon: MessageSquare },
  { id: 'deepseek-reasoner', name: 'Reasoner', provider: 'deepseek', icon: Terminal },
  { id: 'moonshot-v1-8k', name: 'Kimi (8k)', provider: 'moonshot', icon: Moon },
  { id: 'qwen-max', name: 'Qwen Max', provider: 'qwen', icon: MessageSquare },
  { id: 'qwen-plus', name: 'Qwen Plus', provider: 'qwen', icon: MessageSquare },
  { id: 'glm-4', name: '智谱 GLM-4', provider: 'zhipu', icon: Sparkles },
  { id: 'abab6.5-chat', name: 'Minimax abab6.5', provider: 'minimax', icon: Zap },
  { id: 'yi-lightning', name: '零一万物 Yi-Lightning', provider: 'yi', icon: Cpu },
  { id: 'step-1-8k', name: '阶跃星辰 Step-1', provider: 'stepfun', icon: Gauge },

  // === 工具 & 本地 (Tools & Local) ===
  { id: 'llama3', name: 'Llama 3 (Local)', provider: 'ollama', icon: Box },
  { id: 'llama-3.1-70b-versatile', name: 'Groq Llama 3.1', provider: 'groq', icon: Gauge },
  { id: 'pplx-70b-online', name: 'Perplexity Online', provider: 'perplexity', icon: Globe },
  { id: 'mistral-large-latest', name: 'Mistral Large', provider: 'mistral', icon: Search },
];

/**
 * 辅助函数：获取所有已配置并启用的厂商 ID
 * 用于前端过滤模型选择器
 */
export const getEnabledProviders = (config: any) => {
  return Object.keys(config).filter(key => config[key].enabled && config[key].apiKey);
};