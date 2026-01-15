"use client";

import React, { useEffect, useState, useRef, useCallback, useMemo, forwardRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('ThemeSwitcher');

type Theme = 'default' | 'ocean' | 'sakura';

export interface ThemeConfig {
  name: string;
  color: string;
  description?: string;
}

export interface ThemeSwitcherProps {
  themes?: Record<Theme, ThemeConfig>;
  className?: string;
  ariaLabel?: string;
  onThemeChange?: (theme: Theme) => void;
}

const ThemeSwitcher = forwardRef<HTMLDivElement, ThemeSwitcherProps>(
  ({ themes: customThemes, className, ariaLabel, onThemeChange }, ref) => {
    const [isOpen, setIsOpen] = useState(false);
    const internalRef = useRef<HTMLDivElement>(null);
    const dropdownRef = ref || internalRef;
    const buttonRef = useRef<HTMLButtonElement>(null);
    const menuItemsRef = useRef<(HTMLButtonElement | null)[]>([]);
    const isTransitioningRef = useRef(false);

    const [theme, setTheme] = useState<Theme>(() => {
      if (typeof window !== 'undefined') {
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme && ['default', 'ocean', 'sakura'].includes(savedTheme)) {
          return savedTheme as Theme;
        }
      }
      return 'default';
    });

    const themes = useMemo(() => {
      return customThemes || {
        default: {
          name: '🍊 暖阳 (Default)',
          color: '#FF6600',
          description: '温暖的橙色主题',
        },
        ocean: {
          name: '🌊 深海 (Ocean)',
          color: '#00BFFF',
          description: '清新的蓝色主题',
        },
        sakura: {
          name: '🌸 樱花 (Sakura)',
          color: '#FFB6C1',
          description: '柔和的粉色主题',
        },
      };
    }, [customThemes]);

    const themeKeys = useMemo(() => Object.keys(themes) as Theme[], [themes]);

    useEffect(() => {
      logger.debug('render', 'ThemeSwitcher rendering', { 
        currentTheme: theme, 
        isOpen, 
        themeCount: themeKeys.length 
      });
    }, [theme, isOpen, themeKeys]);

    const handleThemeChange = useCallback((newTheme: Theme) => {
      if (isTransitioningRef.current) return;
      
      logger.info('handleThemeChange', 'Theme changed', { 
        oldTheme: theme, 
        newTheme,
        themeName: themes[newTheme].name 
      });
      
      isTransitioningRef.current = true;
      setTheme(newTheme);
      setIsOpen(false);
      
      if (typeof window !== 'undefined') {
        localStorage.setItem('theme', newTheme);
        
        const root = document.documentElement;
        root.style.setProperty('--theme-transition', 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)');
        
        if (theme === 'default') {
          root.removeAttribute('data-theme');
        } else {
          root.setAttribute('data-theme', newTheme);
        }
        
        setTimeout(() => {
          root.style.removeProperty('--theme-transition');
          isTransitioningRef.current = false;
        }, 300);
      }
      
      onThemeChange?.(newTheme);
    }, [theme, themes, onThemeChange]);

    const toggleDropdown = useCallback(() => {
      const newState = !isOpen;
      setIsOpen(newState);
      logger.debug('toggleDropdown', 'Dropdown toggled', { isOpen: newState });
      
      if (newState) {
        setTimeout(() => {
          if (menuItemsRef.current[0]) {
            menuItemsRef.current[0].focus();
          }
        }, 100);
      }
    }, [isOpen]);

    const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>) => {
      switch (event.key) {
        case 'Enter':
        case ' ':
        case 'ArrowDown':
          event.preventDefault();
          toggleDropdown();
          break;
        case 'Escape':
          event.preventDefault();
          if (isOpen) {
            setIsOpen(false);
          }
          break;
      }
    }, [isOpen, toggleDropdown]);

    const handleMenuKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          const nextIndex = (index + 1) % themeKeys.length;
          menuItemsRef.current[nextIndex]?.focus();
          break;
        case 'ArrowUp':
          event.preventDefault();
          const prevIndex = (index - 1 + themeKeys.length) % themeKeys.length;
          menuItemsRef.current[prevIndex]?.focus();
          break;
        case 'Escape':
          event.preventDefault();
          setIsOpen(false);
          buttonRef.current?.focus();
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          handleThemeChange(themeKeys[index]);
          break;
        case 'Tab':
          setIsOpen(false);
          break;
        case 'Home':
          event.preventDefault();
          menuItemsRef.current[0]?.focus();
          break;
        case 'End':
          event.preventDefault();
          menuItemsRef.current[themeKeys.length - 1]?.focus();
          break;
      }
    }, [themeKeys, handleThemeChange]);

    useEffect(() => {
      if (typeof window !== 'undefined') {
        const root = document.documentElement;
        if (theme === 'default') {
          root.removeAttribute('data-theme');
        } else {
          root.setAttribute('data-theme', theme);
        }
        logger.debug('updateTheme', 'Document theme updated', { theme });
      }
    }, [theme]);

    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (dropdownRef && 'current' in dropdownRef && dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
          setIsOpen(false);
        }
      };

      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }, [dropdownRef]);

    const currentThemeConfig = themes[theme];

    return (
      <div className={cn("relative", className)} ref={dropdownRef as React.RefObject<HTMLDivElement>}>
        <button
          ref={buttonRef}
          className="flex items-center gap-2 px-4 py-2 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 shadow-sm hover:shadow-md hover:bg-gray-50 dark:hover:bg-gray-750 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 dark:focus:ring-offset-gray-900 transition-all duration-300 ease-in-out"
          onClick={toggleDropdown}
          onKeyDown={handleKeyDown}
          aria-label={ariaLabel || 'Change theme'}
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          aria-controls="theme-menu"
        >
          <div
            className="w-4 h-4 rounded-full border-2 border-white shadow-sm transition-all duration-300 ease-in-out hover:scale-110 active:scale-95"
            style={{ backgroundColor: currentThemeConfig.color }}
            aria-hidden="true"
          />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors duration-300">
            {currentThemeConfig.name}
          </span>
          <ChevronDown 
            className={cn(
              "w-4 h-4 text-gray-500 transition-all duration-300 ease-in-out",
              isOpen ? 'rotate-180' : ''
            )} 
            aria-hidden="true"
          />
        </button>

        {isOpen && (
          <div
            id="theme-menu"
            className="absolute top-full right-0 mt-2 w-56 bg-white/95 dark:bg-gray-800/95 backdrop-blur-sm rounded-lg border border-gray-200 dark:border-gray-700 shadow-xl overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200 z-50"
            role="listbox"
            aria-label="Theme options"
          >
            {themeKeys.map((key, index) => {
              const isActive = theme === key;
              const { name, color, description } = themes[key];
              
              return (
                <button
                  key={key}
                  ref={(el) => { 
                    menuItemsRef.current[index] = el; 
                  }}
                  role="option"
                  aria-selected={isActive}
                  className={cn(
                    "flex items-center gap-3 px-4 py-3 w-full text-left transition-all duration-300 ease-in-out outline-none",
                    "focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 dark:focus:ring-offset-gray-900",
                    isActive 
                      ? 'bg-primary/10 text-primary border-l-4 border-primary' 
                      : 'hover:bg-gray-100 dark:hover:bg-gray-700 border-l-4 border-transparent'
                  )}
                  onClick={() => handleThemeChange(key)}
                  onKeyDown={(e) => handleMenuKeyDown(e, index)}
                  aria-label={`Switch to ${name} theme${description ? `: ${description}` : ''}`}
                >
                  <div
                    className={cn(
                      "w-4 h-4 rounded-full border-2 border-background shadow-sm transition-all duration-300 ease-in-out",
                      isActive && "ring-2 ring-primary ring-offset-2"
                    )}
                    style={{ backgroundColor: color }}
                    aria-hidden="true"
                  />
                  <div className="flex flex-col">
                    <span className={cn(
                      "text-sm font-medium transition-colors duration-300",
                      isActive ? "text-primary" : "text-foreground"
                    )}>
                      {name}
                    </span>
                    {description && (
                      <span className="text-xs text-gray-500 dark:text-gray-400 transition-colors duration-300">
                        {description}
                      </span>
                    )}
                  </div>
                  {isActive && (
                    <svg
                      className="w-4 h-4 ml-auto text-primary animate-in fade-in zoom-in duration-200"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }
);

ThemeSwitcher.displayName = 'ThemeSwitcher';

export default ThemeSwitcher;