"use client";

import React, { useEffect, useState, useRef } from 'react';
import { ChevronDown } from 'lucide-react';

// 主题类型定义
type Theme = 'default' | 'ocean' | 'sakura';

const ThemeSwitcher: React.FC = () => {
  // 初始值固定为'default'，避免服务端渲染时访问localStorage
  const [theme, setTheme] = useState<Theme>('default');
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 主题配置
  const themes = {
    default: {
      name: '🍊 暖阳 (Default)',
      color: '#FF6600',
    },
    ocean: {
      name: '🌊 深海 (Ocean)',
      color: '#00BFFF',
    },
    sakura: {
      name: '🌸 樱花 (Sakura)',
      color: '#FFB6C1',
    },
  };

  // 更新主题
  const handleThemeChange = (newTheme: Theme) => {
    setTheme(newTheme);
    setIsOpen(false);
    if (typeof window !== 'undefined') {
      localStorage.setItem('theme', newTheme);
    }
  };

  // 在客户端挂载后读取localStorage并初始化主题
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const savedTheme = localStorage.getItem('theme');
      if (savedTheme && Object.keys(themes).includes(savedTheme)) {
        const newTheme = savedTheme as Theme;
        setTheme(newTheme);
        
        // 更新html标签的data-theme属性
        const root = document.documentElement;
        if (newTheme === 'default') {
          root.removeAttribute('data-theme');
        } else {
          root.setAttribute('data-theme', newTheme);
        }
      }
    }
  }, []);

  // 当主题变化时更新 data-theme 属性
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const root = document.documentElement;
      if (theme === 'default') {
        root.removeAttribute('data-theme');
      } else {
        root.setAttribute('data-theme', theme);
      }
    }
  }, [theme]);

  // 点击外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/50 border border-gray-200 shadow-sm hover:bg-white/80 transition-all duration-200"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Change theme"
      >
        {/* Color Dot */}
        <div
          className="w-4 h-4 rounded-full border-2 border-white shadow-sm"
          style={{ backgroundColor: themes[theme].color }}
        />
        {/* Theme Name */}
        <span className="text-sm font-medium text-gray-700">{themes[theme].name}</span>
        {/* Down Arrow */}
        <ChevronDown className="w-4 h-4 text-gray-500" />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-48 bg-white/90 backdrop-blur-sm rounded-lg border border-gray-200 shadow-lg overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200 z-50">
          {Object.entries(themes).map(([key, { name, color }]) => (
            <button
              key={key}
              className={`flex items-center gap-3 px-4 py-3 w-full text-left transition-colors ${theme === key ? 'bg-primary/10 text-primary' : 'hover:bg-gray-100'}`}
              onClick={() => handleThemeChange(key as Theme)}
              aria-label={`Switch to ${name} theme`}
            >
              {/* Color Dot */}
              <div
                className="w-4 h-4 rounded-full border-2 border-white shadow-sm"
                style={{ backgroundColor: color }}
              />
              {/* Theme Name */}
              <span className="text-sm font-medium text-gray-700">{name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default ThemeSwitcher;