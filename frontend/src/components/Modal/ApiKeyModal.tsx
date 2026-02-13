import React, { useState } from 'react';
import { Modal, Input, Switch, Button, Badge, Space, Alert } from 'antd';
import { Lock, Check, AlertCircle, RefreshCw, Trash2, ChevronRight, Server, Cloud, Globe } from 'lucide-react';
import { useApiStore, ProviderConfig } from '@/store/useApiStore';
import type { CheckboxChangeEvent } from 'antd';
import { useAppTheme } from '@/components/providers/LobeProvider';

interface ApiKeyModalProps {
  open: boolean;
  onClose: () => void;
}

// 服务商配置信息
const providerInfo = {
  openai: {
    name: 'OpenAI',
    description: 'OpenAI GPT 系列模型',
    icon: <Globe className="w-4 h-4" />,
    fields: ['apiKey', 'proxyUrl']
  },
  azure: {
    name: 'Azure OpenAI',
    description: 'Azure 托管的 OpenAI 模型',
    icon: <Cloud className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint', 'deploymentName', 'apiVersion']
  },
  google: {
    name: 'Google Gemini',
    description: 'Google Gemini 系列模型',
    icon: <Globe className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  anthropic: {
    name: 'Anthropic Claude',
    description: 'Anthropic Claude 系列模型',
    icon: <Cloud className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  deepseek: {
    name: 'DeepSeek',
    description: '深度求索大模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  moonshot: {
    name: 'Moonshot',
    description: '月之暗面 Kimi 模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  qwen: {
    name: 'Qwen',
    description: '通义千问 (阿里云 DashScope)',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  zhipu: {
    name: 'Zhipu AI',
    description: '智谱 GLM 大模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  minimax: {
    name: 'MiniMax',
    description: '海螺大模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  yi: {
    name: 'Yi',
    description: '零一万物大模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  stepfun: {
    name: 'StepFun',
    description: '阶跃星辰大模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  ollama: {
    name: 'Ollama',
    description: '本地运行的大模型',
    icon: <Server className="w-4 h-4" />,
    fields: ['endpoint']
  },
  groq: {
    name: 'Groq',
    description: '极速推理模型',
    icon: <Cloud className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  perplexity: {
    name: 'Perplexity',
    description: '联网搜索模型',
    icon: <Globe className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  },
  mistral: {
    name: 'Mistral',
    description: '法国开源模型',
    icon: <Cloud className="w-4 h-4" />,
    fields: ['apiKey', 'endpoint']
  }
};

const ApiKeyModal: React.FC<ApiKeyModalProps> = ({ open, onClose }) => {
  const { isDarkMode } = useAppTheme();
  const { config, setProviderConfig, getProviderConfig } = useApiStore();
  const [selectedProvider, setSelectedProvider] = useState<keyof typeof config>('openai');
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<{ success: boolean; message: string } | null>(null);

  // 处理服务商选择
  const handleProviderSelect = (provider: keyof typeof config) => {
    setSelectedProvider(provider);
    setCheckResult(null);
  };

  // 处理配置更新
  const handleConfigUpdate = (field: keyof ProviderConfig, value: any) => {
    setProviderConfig(selectedProvider, field, value);
    setCheckResult(null);
  };

  // 检查连接
  const handleCheckConnection = async () => {
    setChecking(true);
    setCheckResult(null);

    try {
      const provider = selectedProvider;
      const config = currentConfig;

      // 构建请求头
      const headers = {
        'X-Api-Key': config.apiKey || '',
        'X-Provider-Endpoint': config.endpoint || ''
      };

      // 发送请求到后端的 /api/v1/models/check 端点
      const response = await fetch(`/api/v1/models/check?provider=${provider}`, {
        method: 'GET',
        headers
      });

      if (response.ok) {
        // 连接成功
        setCheckResult({ success: true, message: '连接成功！' });
      } else {
        // 连接失败，获取错误信息
        const errorData = await response.json();
        setCheckResult({ success: false, message: errorData.detail || '连接失败，请检查配置' });
      }
    } catch (error) {
      setCheckResult({ success: false, message: '连接失败，请检查网络或配置' });
    } finally {
      setChecking(false);
    }
  };

  // 清除配置
  const handleClearConfig = () => {
    const provider = selectedProvider;
    const defaultConfig = {
      enabled: false,
      apiKey: '',
      endpoint: providerInfo[provider].fields.includes('endpoint') ? (initialConfig[provider]?.endpoint || '') : '',
      proxyUrl: '',
      deploymentName: '',
      apiVersion: ''
    };

    Object.keys(defaultConfig).forEach(field => {
      setProviderConfig(provider, field as keyof ProviderConfig, defaultConfig[field as keyof typeof defaultConfig]);
    });

    setCheckResult(null);
  };

  // 获取初始配置
  const initialConfig = {
    openai: { enabled: true, apiKey: '', proxyUrl: '', endpoint: 'https://api.openai.com/v1' },
    azure: { enabled: false, apiKey: '', endpoint: '', deploymentName: '', apiVersion: '2024-02-15-preview' },
    google: { enabled: false, apiKey: '', endpoint: 'https://generativelanguage.googleapis.com/v1beta/openai/' },
    anthropic: { enabled: false, apiKey: '', endpoint: 'https://api.anthropic.com' },
    deepseek: { enabled: false, apiKey: '', endpoint: 'https://api.deepseek.com/v1' },
    moonshot: { enabled: false, apiKey: '', endpoint: 'https://api.moonshot.cn/v1' },
    qwen: { enabled: false, apiKey: '', endpoint: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
    zhipu: { enabled: false, apiKey: '', endpoint: 'https://open.bigmodel.cn/api/paas/v4' },
    minimax: { enabled: false, apiKey: '', endpoint: 'https://api.minimax.chat/v1' },
    yi: { enabled: false, apiKey: '', endpoint: 'https://api.lingyiwanwu.com/v1' },
    stepfun: { enabled: false, apiKey: '', endpoint: 'https://api.stepfun.com/v1' },
    ollama: { enabled: false, apiKey: 'ollama', endpoint: 'http://localhost:11434/v1' },
    groq: { enabled: false, apiKey: '', endpoint: 'https://api.groq.com/openai/v1' },
    perplexity: { enabled: false, apiKey: '', endpoint: 'https://api.perplexity.ai' },
    mistral: { enabled: false, apiKey: '', endpoint: 'https://api.mistral.ai/v1' }
  };

  // 获取当前选中的配置
  const currentConfig = getProviderConfig(selectedProvider);
  const isEnabled = currentConfig.enabled;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <Space size={8} align="center">
          <span>API Key 管理</span>
          <Badge status="success" text="本地存储/安全" />
        </Space>
      }
      width={900}
      height={600}
    >
      <div className="flex h-full overflow-hidden">
        {/* 左侧服务商列表 */}
        <div className={`w-1/4 ${isDarkMode ? 'dark:bg-gray-800 border-r border-gray-700' : 'bg-gray-50 border-r border-gray-200'} overflow-y-auto`}>
          {Object.keys(config).map((provider) => {
            const providerKey = provider as keyof typeof config;
            const isActive = providerKey === selectedProvider;
            const isEnabled = config[providerKey].enabled;

            return (
              <div
                key={provider}
                className={`flex items-center justify-between px-4 py-3 cursor-pointer transition-colors ${
                  isActive 
                    ? (isDarkMode ? 'dark:bg-gray-700' : 'bg-gray-200') 
                    : (isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100')
                }`}
                onClick={() => handleProviderSelect(providerKey)}
              >
                <div className="flex items-center space-x-2">
                  <span className={isDarkMode ? 'text-gray-400' : 'text-gray-500'}>{providerInfo[providerKey]?.icon || <Server className="w-4 h-4" />}</span>
                  <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-200' : 'text-gray-900'}`}>{providerInfo[providerKey]?.name || provider}</span>
                </div>
                {isEnabled && (
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                )}
              </div>
            );
          })}
        </div>

        {/* 右侧详细配置表单 */}
        <div className={`w-3/4 p-6 overflow-y-auto ${isDarkMode ? 'dark:bg-gray-900' : 'bg-white'}`}>
          {selectedProvider && providerInfo[selectedProvider] && (
            <>
              {/* 顶部：服务商名称、描述、全局 Switch 开关 */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className={`text-lg font-semibold ${isDarkMode ? 'text-gray-100' : 'text-gray-900'}`}>{providerInfo[selectedProvider].name}</h3>
                  <p className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'} mt-1`}>{providerInfo[selectedProvider].description}</p>
                </div>
                <Switch
                  checked={isEnabled}
                  onChange={(checked: boolean) => handleConfigUpdate('enabled', checked)}
                />
              </div>

              {/* 中间：动态表单 */}
              <div className={`space-y-4 transition-opacity duration-300 ${
                isEnabled ? 'opacity-100' : 'opacity-50 pointer-events-none'
              }`}>
                {/* API Key */}
                {providerInfo[selectedProvider].fields.includes('apiKey') && selectedProvider !== 'ollama' && (
                  <div>
                    <label className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'} mb-1`}>API Key</label>
                    <Input
                      type="password"
                      value={currentConfig.apiKey}
                      onChange={(e) => handleConfigUpdate('apiKey', e.target.value)}
                      placeholder="请输入 API Key"
                      prefix={<Lock className="w-4 h-4" />}
                      className="w-full"
                    />
                  </div>
                )}

                {/* Endpoint */}
                {providerInfo[selectedProvider].fields.includes('endpoint') && (
                  <div>
                    <label className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'} mb-1`}>Endpoint</label>
                    <Input
                      value={currentConfig.endpoint || ''}
                      onChange={(e) => handleConfigUpdate('endpoint', e.target.value)}
                      placeholder="请输入 Endpoint"
                      className="w-full"
                    />
                  </div>
                )}

                {/* Proxy URL (仅 OpenAI) */}
                {selectedProvider === 'openai' && (
                  <div>
                    <label className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'} mb-1`}>Proxy URL (选填)</label>
                    <Input
                      value={currentConfig.proxyUrl || ''}
                      onChange={(e) => handleConfigUpdate('proxyUrl', e.target.value)}
                      placeholder="请输入代理 URL"
                      className="w-full"
                    />
                  </div>
                )}

                {/* Deployment Name (仅 Azure) */}
                {selectedProvider === 'azure' && (
                  <div>
                    <label className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'} mb-1`}>Deployment Name</label>
                    <Input
                      value={currentConfig.deploymentName || ''}
                      onChange={(e) => handleConfigUpdate('deploymentName', e.target.value)}
                      placeholder="请输入 Deployment Name"
                      className="w-full"
                    />
                  </div>
                )}

                {/* API Version (仅 Azure) */}
                {selectedProvider === 'azure' && (
                  <div>
                    <label className={`block text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'} mb-1`}>API Version</label>
                    <Input
                      value={currentConfig.apiVersion || ''}
                      onChange={(e) => handleConfigUpdate('apiVersion', e.target.value)}
                      placeholder="请输入 API Version"
                      className="w-full"
                    />
                  </div>
                )}
              </div>

              {/* 连接检查结果 */}
              {checkResult && (
                <Alert
                  type={checkResult.success ? 'success' : 'error'}
                  title={checkResult.message}
                  className="mt-4"
                />
              )}

              {/* 底部：按钮 */}
              <div className="mt-8 flex justify-end space-x-4">
                <Button
                  danger
                  onClick={handleClearConfig}
                  icon={<Trash2 className="w-4 h-4" />}
                >
                  清除
                </Button>
                <Button
                  type="primary"
                  onClick={handleCheckConnection}
                  loading={checking}
                  icon={checking ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  disabled={!isEnabled}
                >
                  检查连接
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default ApiKeyModal;
