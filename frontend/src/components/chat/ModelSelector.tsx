import React, { useEffect } from 'react';
import { Select, Icon } from '@lobehub/ui';
import { useApiStore } from '@/store/useApiStore';
import { MODEL_LIST } from '@/store/models';
import { Settings2 } from 'lucide-react';

interface ModelSelectorProps {
  value: string; // 当前选中的模型ID
  onChange: (modelId: string, provider: string) => void; // 回调：同时返回模型ID和厂商ID
  onOpenSettings: () => void; // 如果没模型可用，引导去设置
}

export const ModelSelector = ({ value, onChange, onOpenSettings }: ModelSelectorProps) => {
  // 1. 从 Store 获取所有配置
  const config = useApiStore((s) => s.config);

  // 2. 计算可用模型列表 (Derived State)
  const availableOptions = MODEL_LIST.filter((model) => {
    const providerConfig = config[model.provider as keyof typeof config];
    // 判定标准：厂商存在 + 已启用 + (有Key 或者 是Ollama/本地模型)
    return (
      providerConfig && 
      providerConfig.enabled && 
      (providerConfig.apiKey || model.provider === 'ollama')
    );
  }).map((model) => ({
    label: (
      <div className="flex items-center gap-2 min-w-0">
        <Icon icon={model.icon} size={16} />
        <span className="flex-1 min-w-0 truncate">{model.name}</span>
        <span className="text-xs text-gray-400 ml-2 whitespace-nowrap">{model.provider}</span>
      </div>
    ),
    value: model.id,
    // 我们可以把元数据绑在 option 上方便查找
    provider: model.provider 
  }));

  // 3. 自动纠正逻辑：
  // 如果当前选中的模型（value）因为用户把 Key 删了而变得不可用，
  // 自动切换到列表里的第一个可用模型。
  useEffect(() => {
    if (availableOptions.length > 0) {
      const isCurrentValid = availableOptions.some(opt => opt.value === value);
      if (!isCurrentValid) {
        // 自动选中第一个
        const first = availableOptions[0];
        // 这里我们需要反查一下 provider
        const modelMeta = MODEL_LIST.find(m => m.id === first.value);
        if (modelMeta) {
            onChange(first.value, modelMeta.provider);
        }
      }
    }
  }, [availableOptions.length, value]); // 依赖项：可用列表长度变化时检测

  // 4. 空状态处理
  if (availableOptions.length === 0) {
    return (
      <div 
        onClick={onOpenSettings}
        className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 px-3 py-1.5 rounded cursor-pointer hover:bg-amber-100 transition-colors"
      >
        <Icon icon={Settings2} size={14} />
        <span>未配置模型，点击设置</span>
      </div>
    );
  }

  return (
    <Select
      value={value}
      options={availableOptions}
      onChange={(newValue) => {
         // 当用户改变选择时，我们需要找到这个模型属于哪个 provider
         const modelMeta = MODEL_LIST.find(m => m.id === newValue);
         if (modelMeta) {
             onChange(newValue, modelMeta.provider);
         }
      }}
      // 样式微调，让它看起来像个胶囊
      variant="borderless" 
      style={{ width: 200 }}
      className="truncate hover:bg-gray-50"
    />
  );
};