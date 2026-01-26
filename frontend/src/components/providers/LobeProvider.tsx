'use client';

import React, { createContext, useContext, ReactNode, useEffect, useState, useMemo } from 'react';
import { ThemeProvider } from '@lobehub/ui';
// 1. 引入 Ant Design 核心组件：ConfigProvider 用于配置，App 用于挂载变量
import { ConfigProvider, App, theme as antTheme } from 'antd';
import type { NeutralColors } from '@lobehub/ui';

// 官方预设颜色列表
const DEFAULT_PRESETS = [
  'blue', 'purple', 'green', 'orange', 'gold', 'cyan',
  'red', 'magenta', 'volcano', 'geekblue', 'lime'
];

// 预设颜色映射：将预设颜色名称转换为对应的 HEX 值
const PRESET_COLOR_MAP: Record<string, string> = {
  blue: '#0072F5',
  purple: '#BD54C6',
  green: '#78B885',
  orange: '#F1AD63',
  gold: '#EAB85E',
  cyan: '#00B8D9',
  red: '#F4416C',
  magenta: '#E34BA9',
  volcano: '#EC5E41',
  geekblue: '#0072F5',
  lime: '#4CAF50',
};

interface AppThemeContextType {
  mode: 'light' | 'dark';
  setMode: (mode: 'light' | 'dark') => void;
  primaryColor: string;
  setPrimaryColor: (color: string) => void;
  neutralColor: NeutralColors;
  setNeutralColor: (color: NeutralColors) => void;
}

const AppThemeContext = createContext<AppThemeContextType | undefined>(undefined);

export const useAppTheme = () => {
  const context = useContext(AppThemeContext);
  if (context === undefined) {
    throw new Error('useAppTheme must be used within an AppThemeProvider');
  }
  return context;
};

interface LobeProviderProps {
  children: ReactNode;
}

export const LobeProvider = ({ children }: LobeProviderProps) => {
  const [mode, setMode] = useState<'light' | 'dark'>('light');
  const [primaryColor, setPrimaryColor] = useState<string>('blue');
  const [neutralColor, setNeutralColor] = useState<NeutralColors>('slate');
  const [isMounted, setIsMounted] = useState(false);

  // --- 挂载与状态同步逻辑 (保持原样) ---
  useEffect(() => {
    setIsMounted(true);
    const savedMode = localStorage.getItem('mode');
    if (savedMode === 'light' || savedMode === 'dark') {
      setMode(savedMode);
    } else {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      setMode(mediaQuery.matches ? 'dark' : 'light');
    }
    const savedColor = localStorage.getItem('APP_PRIMARY_COLOR');
    if (savedColor) setPrimaryColor(savedColor);
  }, []);

  useEffect(() => {
    if (isMounted) localStorage.setItem('APP_PRIMARY_COLOR', primaryColor);
  }, [primaryColor, isMounted]);

  useEffect(() => {
    if (isMounted) localStorage.setItem('mode', mode);
  }, [mode, isMounted]);

  useEffect(() => {
    if (!isMounted) return;
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('mode')) setMode(e.matches ? 'dark' : 'light');
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [isMounted]);

  useEffect(() => {
    if (!isMounted) return;
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === 'mode' && event.newValue) setMode(event.newValue as 'light' | 'dark');
      if (event.key === 'APP_PRIMARY_COLOR' && event.newValue) setPrimaryColor(event.newValue);
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [isMounted]);

  // --- 样式逻辑核心 --- 

  // 计算是否为预设颜色
  const isPreset = DEFAULT_PRESETS.includes(primaryColor);
  
  // 获取实际的 HEX 颜色值
  const actualColor = isPreset ? PRESET_COLOR_MAP[primaryColor] || primaryColor : primaryColor;

  // 1. 为了防止 Lobe UI 崩溃或黑屏，我们必须欺骗它
  // 如果是自定义 HEX，告诉外层 "我是蓝色"，让它先生成基础样式
  const customTheme = useMemo(() => {
    return {
      neutralColor,
      primaryColor: isPreset ? primaryColor : 'blue', 
    } as any;
  }, [isPreset, primaryColor, neutralColor]);

  if (!isMounted) {
    return null;
  }

  // 提供给上下文的主题颜色：始终是 HEX 值
  const contextPrimaryColor = actualColor;

  return (
    <AppThemeContext.Provider value={{ mode, setMode, primaryColor: contextPrimaryColor, setPrimaryColor, neutralColor, setNeutralColor }}>
      <ThemeProvider 
        // Key 包含 primaryColor 和 mode，确保切换颜色或模式时都能彻底刷新
        // 同时解决闪屏问题：重建时直接使用正确的主题模式
        key={`${primaryColor}-${mode}`} 
        themeMode={mode} 
        customTheme={customTheme}
      >
        {/* 根据是否为预设颜色动态渲染
           - 预设颜色：使用 ConfigProvider 确保颜色正确应用
           - 自定义颜色：使用 ConfigProvider 强行覆盖 Token
        */}
        <ConfigProvider
          theme={{
            token: { 
              // 直接使用实际的 HEX 颜色
              colorPrimary: actualColor,
              colorInfo: actualColor 
            },
            // 开启 CSS 变量，确保 --ant-color-primary 生成
            // key: 'app' 是为了让样式作用域更稳定
            cssVar: { key: 'app' },
            // 同步暗黑模式算法
            algorithm: mode === 'dark' ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
          }}
        >
          {/* 3. 实体挂载点：App 组件
            ConfigProvider 只是配置，不渲染 DOM。
            App 组件会渲染一个 div，并把 --ant-color-primary 挂在这个 div 上。
            这样内部所有的原生 html 标签（如你的 button）才能继承到这个变量。
          */}
          <App style={{ minHeight: 'inherit', width: 'inherit', display: 'flex', flexDirection: 'column' }}>
            {children}
          </App>
        </ConfigProvider>
      </ThemeProvider>
    </AppThemeContext.Provider>
  );
};