import { MODEL_LIST } from '@/store/models';
import type { ProviderConfig } from '@/store/useApiStore';

type ProviderSettings = Pick<ProviderConfig, 'enabled' | 'apiKey'>;
type ProviderConfigMap = Record<string, ProviderSettings | undefined>;

interface SessionModelConfig {
  model?: string;
  provider?: string;
}

export interface ChatSelection {
  model: string;
  provider: string;
}

const isProviderAvailable = (
  provider: string,
  config: ProviderConfigMap,
): boolean => {
  const providerConfig = config[provider];
  return Boolean(
    providerConfig?.enabled
    && (providerConfig.apiKey || provider === 'ollama'),
  );
};

export const resolveChatSelection = (
  sessionConfig: SessionModelConfig | undefined,
  config: ProviderConfigMap,
): ChatSelection => {
  const sessionModel = MODEL_LIST.find((model) => (
    model.id === sessionConfig?.model
    && model.provider === sessionConfig?.provider
    && isProviderAvailable(model.provider, config)
  ));
  if (sessionModel) {
    return { model: sessionModel.id, provider: sessionModel.provider };
  }

  const firstAvailableModel = MODEL_LIST.find((model) => (
    isProviderAvailable(model.provider, config)
  ));
  if (firstAvailableModel) {
    return { model: firstAvailableModel.id, provider: firstAvailableModel.provider };
  }

  return { model: 'gpt-3.5-turbo', provider: 'openai' };
};
