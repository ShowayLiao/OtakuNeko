"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode, useRef } from 'react';
import { fetchBangumiUser, BangumiUser, login, saveAiToken } from '@/lib/api';
import { readUserInfoFromLocalStorage } from '@/lib/localAuth';

interface Settings {
  username: string;
  bangumiToken?: string;
  aiHost: string;
  aiToken: string;
}

interface SettingsContextType {
  settings: Settings;
  userInfo: BangumiUser | null;
  isRemembered: boolean;
  updateSettings: (newSettings: Partial<Settings>, remember: boolean) => void;
  resetSession: () => void;
  refreshUserInfo: (username: string) => Promise<void>;
  setUserInfo: (userInfo: BangumiUser | null) => void;
}

const defaultSettings: Settings = {
  username: '',
  bangumiToken: '',
  aiHost: 'http://localhost:8000',
  aiToken: ''
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

const STORAGE_KEY = 'otakuneko_settings';
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;

export const SettingsProvider = ({ children }: { children: ReactNode }) => {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [userInfo, setUserInfo] = useState<BangumiUser | null>(null);
  const [isRemembered, setIsRemembered] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const sessionTimerRef = useRef<NodeJS.Timeout | null>(null);

  const clearSessionTimer = () => {
    if (sessionTimerRef.current) {
      clearTimeout(sessionTimerRef.current);
      sessionTimerRef.current = null;
    }
  };

  const startSessionTimer = () => {
    clearSessionTimer();
    sessionTimerRef.current = setTimeout(() => {
      resetSession();
    }, SESSION_TIMEOUT_MS);
  };

  const resetSession = () => {
    clearSessionTimer();
    setSettings({
      username: '',
      bangumiToken: '',
      aiHost: 'http://localhost:8000',
      aiToken: ''
    });
    setUserInfo(null);
    setIsRemembered(false);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      console.error('Error clearing localStorage:', error);
    }
  };

  useEffect(() => {
    const initializeSettingsAndAutoLogin = async () => {
      try {
        const savedSettings = localStorage.getItem(STORAGE_KEY);
        if (savedSettings) {
          const parsed = JSON.parse(savedSettings);
          setSettings({ ...defaultSettings, ...parsed });
          setIsRemembered(true);
          if (parsed.userInfo) {
            setUserInfo(parsed.userInfo);
          }
        }

        // 实现无感登录逻辑
        const cloudMode = process.env.NEXT_PUBLIC_CLOUD_MODE?.toLowerCase() === 'true';
        if (!cloudMode && !settings.username) {
          // 仅在本地模式且尚未有用户名时执行无感登录
          const userInfo = readUserInfoFromLocalStorage();
          
          if (userInfo) {
            const { username, aiHost, aiToken, bangumiId, noBangumiAccount } = userInfo;
            
            try {
              // 1. 自动登录用户
              const loginResponse = await login(username);
              
              // 2. 转换为BangumiUser类型用于上下文
              const bangumiUserInfo: BangumiUser = {
                id: loginResponse.user.id,
                username: loginResponse.user.username,
                nickname: loginResponse.user.nickname,
                sign: loginResponse.user.sign,
                avatar: {
                  large: loginResponse.user.avatar_url || '',
                  medium: loginResponse.user.avatar_url || '',
                  small: loginResponse.user.avatar_url || ''
                },
                bangumi_id: loginResponse.user.bangumi_id || undefined
              };
              
              // 3. 更新用户信息上下文
              setUserInfo(bangumiUserInfo);
              
              // 4. 保存AI Token
              saveAiToken(aiToken);
              
              // 5. 更新设置
              const updatedSettings = {
                username: username,
                bangumiToken: noBangumiAccount ? undefined : bangumiId,
                aiHost: aiHost,
                aiToken: aiToken
              };
              setSettings(updatedSettings);
              
              // 6. 保存到localStorage
              try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({
                  ...updatedSettings,
                  userInfo: bangumiUserInfo
                }));
                setIsRemembered(true);
              } catch (storageError) {
                console.error('Error saving auto-login settings to localStorage:', storageError);
              }
            } catch (loginError) {
              console.error('自动登录失败，需要用户手动登录:', loginError);
              // 自动登录失败，保持默认设置，等待用户手动登录
            }
          }
        }
      } catch (error) {
        console.error('Error initializing settings and auto-login:', error);
      } finally {
        setIsInitialized(true);
      }
    };

    initializeSettingsAndAutoLogin();

    return () => {
      clearSessionTimer();
    };
  }, []);

  const updateSettings = (newSettings: Partial<Settings>, remember: boolean) => {
    const updatedSettings = { ...settings, ...newSettings };
    setSettings(updatedSettings);
    setIsRemembered(remember);

    if (remember) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          ...updatedSettings,
          userInfo
        }));
      } catch (error) {
        console.error('Error saving settings to localStorage:', error);
      }
    } else {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch (error) {
        console.error('Error clearing localStorage:', error);
      }
      startSessionTimer();
    }
  };

  const refreshUserInfo = useCallback(async (username: string) => {
    try {
      const userData = await fetchBangumiUser(username);
      setUserInfo(userData);
      
      if (userData && isRemembered) {
        try {
          const savedSettings = localStorage.getItem(STORAGE_KEY);
          if (savedSettings) {
            const parsed = JSON.parse(savedSettings);
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
              ...parsed,
              userInfo: userData
            }));
          }
        } catch (error) {
          console.error('Error saving userInfo to localStorage:', error);
        }
      }
    } catch (error) {
      console.error('Error fetching user info:', error);
      setUserInfo(null);
    }
  }, [isRemembered]);

  const setUserInfoHandler = (userInfo: BangumiUser | null) => {
    setUserInfo(userInfo);
    
    if (isRemembered && userInfo) {
      try {
        const savedSettings = localStorage.getItem(STORAGE_KEY);
        if (savedSettings) {
          const parsed = JSON.parse(savedSettings);
          localStorage.setItem(STORAGE_KEY, JSON.stringify({
            ...parsed,
            userInfo
          }));
        }
      } catch (error) {
        console.error('Error saving userInfo to localStorage:', error);
      }
    }
  };

  useEffect(() => {
    if (settings.username && isInitialized && !userInfo?.bangumi_id) {
      refreshUserInfo(settings.username);
    }
  }, [settings.username, isInitialized, userInfo?.bangumi_id, refreshUserInfo]);

  if (!isInitialized) {
    return null;
  }

  return (
    <SettingsContext.Provider value={{ settings, userInfo, isRemembered, updateSettings, resetSession, refreshUserInfo, setUserInfo: setUserInfoHandler }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
