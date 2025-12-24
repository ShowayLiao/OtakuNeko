"use client";

import React, { useEffect, useState } from 'react';

interface ThemeSwitcherProps {
  className?: string;
}

type Theme = 'default' | 'ocean' | 'sakura';

const themes: { [key in Theme]: { label: string; color: string } } = {
  default: { label: 'Orange', color: '#FF6600' },
  ocean: { label: 'Ocean', color: '#00BFFF' },
  sakura: { label: 'Sakura', color: '#FFB6C1' }
};

export const ThemeSwitcher: React.FC<ThemeSwitcherProps> = ({ className }) => {
  // 初始值固定为'default'，避免服务端渲染时访问localStorage
  const [currentTheme, setCurrentTheme] = useState<Theme>('default');

  const updateTheme = (theme: Theme) => {
    if (typeof window !== 'undefined') {
      const root = document.documentElement;
      root.setAttribute('data-theme', theme);
      localStorage.setItem('theme', theme);
    }
  };

  // 在客户端挂载后读取localStorage并初始化主题
  useEffect(() => {
    // 确保只在客户端执行
    if (typeof window !== 'undefined') {
      const savedTheme = localStorage.getItem('theme') as Theme;
      if (savedTheme && Object.keys(themes).includes(savedTheme)) {
        // 直接更新DOM和localStorage，然后再更新状态
        updateTheme(savedTheme);
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setCurrentTheme(savedTheme);
      } else {
        // 如果没有保存的主题，初始化data-theme属性为default
        updateTheme('default');
      }
    }
  }, []);

  const handleThemeChange = (theme: Theme) => {
    setCurrentTheme(theme);
    updateTheme(theme);
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {Object.entries(themes).map(([theme, { color }]) => (
        <button
          key={theme}
          onClick={() => handleThemeChange(theme as Theme)}
          className={`w-8 h-8 rounded-full transition-all duration-300 ${currentTheme === theme ? 'ring-2 ring-white scale-110' : ''}`}
          style={{ backgroundColor: color }}
          aria-label={`Switch to ${theme} theme`}
          title={theme === 'default' ? 'Orange Theme' : theme.charAt(0).toUpperCase() + theme.slice(1) + ' Theme'}
        />
      ))}
    </div>
  );
};