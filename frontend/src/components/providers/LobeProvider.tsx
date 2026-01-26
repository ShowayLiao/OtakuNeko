'use client';

import React, { createContext, useContext, ReactNode, useEffect, useState, useMemo } from 'react';
import { ThemeProvider } from '@lobehub/ui';
import { ConfigProvider, App, theme as antTheme } from 'antd';
import type { NeutralColors } from '@lobehub/ui';

// 类型定义
type ThemeAppearance = 'auto' | 'light' | 'dark';

interface AppThemeContextType {
  appearance: ThemeAppearance;        // 用户偏好：自动/亮/暗
  setAppearance: (mode: ThemeAppearance) => void; 
  isDarkMode: boolean;               // 实际渲染结果：是否为暗色
  primaryColor: string;
  setPrimaryColor: (color: string) => void;
  neutralColor: NeutralColors;
  setNeutralColor: (color: NeutralColors) => void;
}

const AppThemeContext = createContext<AppThemeContextType | undefined>(undefined);

export const useAppTheme = () => {
  const context = useContext(AppThemeContext);
  if (!context) throw new Error('useAppTheme must be used within LobeProvider');
  return context;
};

// --- 辅助函数：获取系统是否为暗色 ---
const getSystemIsDarkMode = () => {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
};

// --- 颜色映射表，与 ThemeSwitcher 保持一致 ---
const COLOR_KEY_TO_HEX = {
  purple: '#BD54C6',
  green: '#78B885',
  orange: '#F1AD63',
  gold: '#EAB85E',
  red: '#F4416C',
  magenta: '#E34BA9',
  volcano: '#EC5E41',
  geekblue: '#0072F5',
};

// --- 辅助函数：将颜色 key 转换为十六进制颜色值 ---
const resolvePrimaryColor = (color: string): string => {
  // 如果已经是十六进制颜色值，直接返回
  if (color.startsWith('#')) return color;
  // 否则尝试从映射表中获取
  return COLOR_KEY_TO_HEX[color as keyof typeof COLOR_KEY_TO_HEX] || color;
};

export const LobeProvider = ({ children }: { children: ReactNode }) => {
  // 1. 核心状态：用户偏好 (默认为 auto)
  const [appearance, setAppearance] = useState<ThemeAppearance>('auto');
  // 2. 衍生状态：系统当前是否为暗色
  const [systemIsDark, setSystemIsDark] = useState(false);
  
  const [primaryColor, setPrimaryColor] = useState<string>('#0072F5'); // 默认蓝色 Hex
  const [neutralColor, setNeutralColor] = useState<NeutralColors>('slate');
  const [isMounted, setIsMounted] = useState(false);

  // --- 初始化与监听 ---
  useEffect(() => {
    setIsMounted(true);
    
    // 初始化系统状态
    setSystemIsDark(getSystemIsDarkMode());

    // 读取本地存储
    const savedAppearance = localStorage.getItem('APP_THEME_APPEARANCE') as ThemeAppearance;
    if (savedAppearance) setAppearance(savedAppearance);
    
    const savedColor = localStorage.getItem('APP_PRIMARY_COLOR');
    if (savedColor) setPrimaryColor(savedColor);

    // 监听系统主题变化
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemChange = (e: MediaQueryListEvent) => {
      setSystemIsDark(e.matches);
    };
    
    // 现代浏览器监听方式
    try {
      mediaQuery.addEventListener('change', handleSystemChange);
    } catch (e) {
      // 兼容旧浏览器
      mediaQuery.addListener(handleSystemChange);
    }

    return () => {
      try {
        mediaQuery.removeEventListener('change', handleSystemChange);
      } catch (e) {
        mediaQuery.removeListener(handleSystemChange);
      }
    };
  }, []);

  // --- 持久化存储 ---
  useEffect(() => {
    if (isMounted) {
      localStorage.setItem('APP_THEME_APPEARANCE', appearance);
      localStorage.setItem('APP_PRIMARY_COLOR', primaryColor);
    }
  }, [appearance, primaryColor, isMounted]);

  // --- 核心逻辑：计算最终其实际是 light 还是 dark ---
  const isDarkMode = useMemo(() => {
    if (appearance === 'auto') return systemIsDark;
    return appearance === 'dark';
  }, [appearance, systemIsDark]);

  // 这里的 mode 专门传给 UI 组件库
  const resolvedMode = isDarkMode ? 'dark' : 'light';

  // --- 样式逻辑 (使用 resolvePrimaryColor 处理 primaryColor) ---
  const customTheme = useMemo(() => ({
      neutralColor,
      primaryColor: resolvePrimaryColor(primaryColor), 
    } as any), [primaryColor, neutralColor]);

  if (!isMounted) return null;

  return (
    <AppThemeContext.Provider value={{ 
      appearance, 
      setAppearance, 
      isDarkMode,
      primaryColor, 
      setPrimaryColor, 
      neutralColor, 
      setNeutralColor 
    }}>
      <ThemeProvider 
        key={`${primaryColor}-${resolvedMode}`} 
        themeMode={resolvedMode} 
        customTheme={customTheme}
      >
        <ConfigProvider
          theme={{
            token: { 
              colorPrimary: resolvePrimaryColor(primaryColor),
              colorInfo: resolvePrimaryColor(primaryColor) 
            },
            cssVar: { key: 'app' },
            algorithm: isDarkMode ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
          }}
        >
          <App style={{ minHeight: 'inherit', width: 'inherit', display: 'flex', flexDirection: 'column' }}>
            {children}
          </App>
        </ConfigProvider>
      </ThemeProvider>
    </AppThemeContext.Provider>
  );
};