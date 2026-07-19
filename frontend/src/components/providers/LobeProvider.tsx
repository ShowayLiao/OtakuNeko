'use client';

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { ThemeProvider } from '@lobehub/ui';
import type { NeutralColors, PrimaryColors } from '@lobehub/ui';
import { App, ConfigProvider, theme as antTheme } from 'antd';

type ThemeAppearance = 'auto' | 'light' | 'dark';

interface AppThemeContextType {
  appearance: ThemeAppearance;
  setAppearance: (mode: ThemeAppearance) => void;
  isDarkMode: boolean;
  primaryColor: string;
  setPrimaryColor: (color: string) => void;
  neutralColor: NeutralColors;
  setNeutralColor: (color: NeutralColors) => void;
}

const AppThemeContext = createContext<AppThemeContextType | undefined>(undefined);

const COLOR_KEY_TO_HEX: Record<string, string> = {
  purple: '#BD54C6',
  green: '#78B885',
  orange: '#F1AD63',
  gold: '#EAB85E',
  red: '#F4416C',
  magenta: '#E34BA9',
  volcano: '#EC5E41',
  geekblue: '#0072F5',
};

const resolvePrimaryColor = (color: string): string =>
  color.startsWith('#') ? color : COLOR_KEY_TO_HEX[color] || color;

const getSystemIsDarkMode = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
};

const subscribeToSystemColorScheme = (onChange: () => void): (() => void) => {
  if (typeof window === 'undefined') return () => {};
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  mediaQuery.addEventListener('change', onChange);
  return () => mediaQuery.removeEventListener('change', onChange);
};

export const useAppTheme = (): AppThemeContextType => {
  const context = useContext(AppThemeContext);
  if (!context) throw new Error('useAppTheme must be used within LobeProvider');
  return context;
};

export const LobeProvider = ({ children }: { children: ReactNode }) => {
  const [appearance, setAppearance] = useState<ThemeAppearance>(() => {
    if (typeof window === 'undefined') return 'auto';
    return (localStorage.getItem('APP_THEME_APPEARANCE') as ThemeAppearance) || 'auto';
  });
  const [primaryColor, setPrimaryColor] = useState(() => {
    if (typeof window === 'undefined') return '#0072F5';
    return localStorage.getItem('APP_PRIMARY_COLOR') || '#0072F5';
  });
  const [neutralColor, setNeutralColor] = useState<NeutralColors>('slate');
  const systemIsDark = useSyncExternalStore(
    subscribeToSystemColorScheme,
    getSystemIsDarkMode,
    () => false,
  );

  useEffect(() => {
    localStorage.setItem('APP_THEME_APPEARANCE', appearance);
    localStorage.setItem('APP_PRIMARY_COLOR', primaryColor);
  }, [appearance, primaryColor]);

  const isDarkMode = appearance === 'auto' ? systemIsDark : appearance === 'dark';
  const resolvedMode = isDarkMode ? 'dark' : 'light';
  const customTheme = useMemo(
    () => ({
      neutralColor,
      primaryColor: (primaryColor in COLOR_KEY_TO_HEX ? primaryColor : 'geekblue') as PrimaryColors,
    }),
    [neutralColor, primaryColor],
  );

  return (
    <AppThemeContext.Provider
      value={{
        appearance,
        setAppearance,
        isDarkMode,
        primaryColor,
        setPrimaryColor,
        neutralColor,
        setNeutralColor,
      }}
    >
      <ThemeProvider key={`${primaryColor}-${resolvedMode}`} themeMode={resolvedMode} customTheme={customTheme}>
        <ConfigProvider
          theme={{
            token: {
              colorPrimary: resolvePrimaryColor(primaryColor),
              colorInfo: resolvePrimaryColor(primaryColor),
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
