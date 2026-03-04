export interface PromptConfig {
  persona: string;    // 核心身份
  tone: string;       // 语气风格
  rules: string;      // 行为准则
}

export interface Role {
  id: string;
  name: string;
  avatar: string;
  description: string;
  promptConfig: PromptConfig; // 替代原来的 systemPrompt
  temperature: number;
  isPreset: boolean;
}

export interface Model {
  id: string;
  name: string;
  provider: string;
  icon: string;
}

export const MODEL_LIST: Model[] = [
  // OpenAI
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'openai', icon: 'OpenAI' },
  { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', provider: 'openai', icon: 'OpenAI' },
  { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', provider: 'openai', icon: 'OpenAI' },
  
  // Azure
  { id: 'azure-gpt-4o', name: 'Azure GPT-4o', provider: 'azure', icon: 'Microsoft' },
  { id: 'azure-gpt-4-turbo', name: 'Azure GPT-4 Turbo', provider: 'azure', icon: 'Microsoft' },
  
  // Google
  { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', provider: 'google', icon: 'Google' },
  { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', provider: 'google', icon: 'Google' },
  
  // Anthropic
  { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus', provider: 'anthropic', icon: 'Anthropic' },
  { id: 'claude-3-sonnet-20240229', name: 'Claude 3 Sonnet', provider: 'anthropic', icon: 'Anthropic' },
  
  // 国产模型
  { id: 'deepseek-chat', name: 'DeepSeek R1', provider: 'deepseek', icon: 'DeepSeek' },
  { id: 'moonshot-v1-8k', name: 'Kimi', provider: 'moonshot', icon: 'MoonShot' },
  { id: 'qwen-plus', name: '通义千问 Plus', provider: 'qwen', icon: 'Alibaba' },
  { id: 'glm-4', name: '智谱 GLM-4', provider: 'zhipu', icon: 'ZhiPu' },
  { id: 'abab5.5-chat', name: '海螺 5.5', provider: 'minimax', icon: 'MiniMax' },
  { id: 'yi-34b-chat-20240307', name: '零一万物 Yi-34B', provider: 'yi', icon: '01AI' },
  { id: 'stepfun', name: '阶跃星辰', provider: 'stepfun', icon: 'StepFun' },
  
  // 其他
  { id: 'llama3:8b', name: 'Llama 3 8B', provider: 'ollama', icon: 'Ollama' },
  { id: 'llama3:70b', name: 'Llama 3 70B', provider: 'ollama', icon: 'Ollama' },
  { id: 'mixtral:8x7b', name: 'Mixtral 8x7B', provider: 'ollama', icon: 'Ollama' },
  { id: 'gemma:7b', name: 'Gemma 7B', provider: 'ollama', icon: 'Ollama' },
  { id: 'llama3-groq-8b-8192', name: 'GROQ Llama 3 8B', provider: 'groq', icon: 'Groq' },
  { id: 'llama3-groq-70b-8192', name: 'GROQ Llama 3 70B', provider: 'groq', icon: 'Groq' },
  { id: 'mistral-7b-instruct-v0.2', name: 'Mistral 7B', provider: 'mistral', icon: 'Mistral' },
  { id: 'mistral-large-latest', name: 'Mistral Large', provider: 'mistral', icon: 'Mistral' },
  { id: 'llama-3-sonar-large-32k-online', name: 'Perplexity Sonar', provider: 'perplexity', icon: 'Perplexity' },
];
