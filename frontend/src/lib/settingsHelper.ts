const STORAGE_KEY = 'otakuneko_settings';

interface Settings {
  username: string;
  bangumiToken?: string;
  aiHost: string;
  aiToken: string;
}

const defaultSettings: Settings = {
  username: '',
  bangumiToken: '',
  aiHost: 'http://localhost:8000',
  aiToken: ''
};

const getStoredSettings = (): Settings => {
  if (typeof window === 'undefined') return defaultSettings;
  
  try {
    const savedSettings = localStorage.getItem(STORAGE_KEY);
    if (savedSettings) {
      const parsed = JSON.parse(savedSettings);
      return { ...defaultSettings, ...parsed };
    }
  } catch (error) {
    console.error('Error getting settings from localStorage:', error);
  }
  
  return defaultSettings;
};

export const getUsername = (): string => {
  return getStoredSettings().username;
};

export const getBangumiToken = (): string | undefined => {
  const token = getStoredSettings().bangumiToken;
  return token && token.trim() ? token : undefined;
};

export const getAiHost = (): string => {
  return getStoredSettings().aiHost;
};

export const getAiToken = (): string => {
  return getStoredSettings().aiToken;
};

export const getApiConfig = () => {
  return {
    username: getUsername(),
    bangumiToken: getBangumiToken(),
    aiHost: getAiHost(),
    aiToken: getAiToken()
  };
};
