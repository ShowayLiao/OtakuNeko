// 环境模式判断
const IS_CLOUD_MODE = process.env.NEXT_PUBLIC_CLOUD_MODE === 'true';

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

const saveSettings = (settings: Partial<Settings>): void => {
  if (typeof window === 'undefined') return;
  
  try {
    const currentSettings = getStoredSettings();
    const updatedSettings = { ...currentSettings, ...settings };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedSettings));
  } catch (error) {
    console.error('Error saving settings to localStorage:', error);
  }
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

export const saveAiHost = (aiHost: string): void => {
  saveSettings({ aiHost });
};

export const saveAiToken = (aiToken: string): void => {
  saveSettings({ aiToken });
};

export const saveUsername = (username: string): void => {
  saveSettings({ username });
};

export const getApiConfig = () => {
  return {
    username: getUsername(),
    bangumiToken: getBangumiToken(),
    aiHost: getAiHost(),
    aiToken: getAiToken()
  };
};
