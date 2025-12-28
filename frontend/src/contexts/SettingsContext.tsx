"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useRef } from 'react';
import { fetchBangumiUser, BangumiUser } from '@/lib/api';

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
    } catch (error) {
      console.error('Error loading settings from localStorage:', error);
    } finally {
      setIsInitialized(true);
    }

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

  const refreshUserInfo = async (username: string) => {
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
  };

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
  }, [settings.username, isInitialized, userInfo?.bangumi_id]);

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
