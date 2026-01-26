'use client';

import { ThemeSwitch } from '@lobehub/ui';
import { useAppTheme } from '@/components/providers/LobeProvider';

export const ThemeModeSwitcher = () => {
  const { mode, setMode } = useAppTheme();

  // 将 ThemeSwitch 的主题模式转换为全局模式
  const handleThemeSwitch = (newThemeMode: 'auto' | 'light' | 'dark') => {
    if (newThemeMode === 'auto') {
      // 自动模式：根据系统主题设置
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      setMode(mediaQuery.matches ? 'dark' : 'light');
    } else {
      // 手动模式：直接使用选择的模式
      setMode(newThemeMode);
    }
  };

  return (
    <ThemeSwitch 
      size="middle" 
      type="icon" 
      variant="borderless" 
      onThemeSwitch={handleThemeSwitch} 
      themeMode={mode as 'light' | 'dark'} 
    />
  );
};