"use client";

import React, {
  createContext,
  useContext,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { ThemeProvider } from "@lobehub/ui";
import type { NeutralColors, PrimaryColors } from "@lobehub/ui";
import { App, ConfigProvider, theme as antTheme } from "antd";

type ThemeAppearance = "auto" | "light" | "dark";

interface AppThemeContextType {
  appearance: ThemeAppearance;
  setAppearance: (mode: ThemeAppearance) => void;
  isDarkMode: boolean;
  primaryColor: string;
  setPrimaryColor: (color: string) => void;
  neutralColor: NeutralColors;
  setNeutralColor: (color: NeutralColors) => void;
}

const AppThemeContext = createContext<AppThemeContextType | undefined>(
  undefined,
);

const COLOR_KEY_TO_HEX: Record<string, string> = {
  purple: "#BD54C6",
  green: "#78B885",
  orange: "#F1AD63",
  gold: "#EAB85E",
  red: "#F4416C",
  magenta: "#E34BA9",
  volcano: "#EC5E41",
  geekblue: "#0072F5",
};

const resolvePrimaryColor = (color: string): string =>
  color.startsWith("#") ? color : COLOR_KEY_TO_HEX[color] || color;

const getSystemIsDarkMode = (): boolean => {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
};

const subscribeToSystemColorScheme = (onChange: () => void): (() => void) => {
  if (typeof window === "undefined") return () => {};
  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  mediaQuery.addEventListener("change", onChange);
  return () => mediaQuery.removeEventListener("change", onChange);
};

export const useAppTheme = (): AppThemeContextType => {
  const context = useContext(AppThemeContext);
  if (!context) throw new Error("useAppTheme must be used within LobeProvider");
  return context;
};

const THEME_CHANGED_EVENT = "otakuneko-theme-changed";
const subscribeToTheme = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  window.addEventListener(THEME_CHANGED_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(THEME_CHANGED_EVENT, onChange);
  };
};
const readAppearance = (): ThemeAppearance => {
  const value = localStorage.getItem("APP_THEME_APPEARANCE");
  return value === "light" || value === "dark" ? value : "auto";
};
const readPrimaryColor = () =>
  localStorage.getItem("APP_PRIMARY_COLOR") || "#0072F5";
const subscribeToHydration = () => () => {};

export const LobeProvider = ({ children }: { children: ReactNode }) => {
  // The server and first hydration render use identical snapshots. Browser
  // preferences are applied after hydration, without overwriting saved values.
  const appearance = useSyncExternalStore(
    subscribeToTheme,
    readAppearance,
    () => "auto" as ThemeAppearance,
  );
  const primaryColor = useSyncExternalStore(
    subscribeToTheme,
    readPrimaryColor,
    () => "#0072F5",
  );
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  const setAppearance = (mode: ThemeAppearance) => {
    localStorage.setItem("APP_THEME_APPEARANCE", mode);
    window.dispatchEvent(new Event(THEME_CHANGED_EVENT));
  };
  const setPrimaryColor = (color: string) => {
    localStorage.setItem("APP_PRIMARY_COLOR", color);
    window.dispatchEvent(new Event(THEME_CHANGED_EVENT));
  };
  const [neutralColor, setNeutralColor] = useState<NeutralColors>("slate");
  const systemIsDark = useSyncExternalStore(
    subscribeToSystemColorScheme,
    getSystemIsDarkMode,
    () => false,
  );

  const isDarkMode =
    appearance === "auto" ? systemIsDark : appearance === "dark";
  const resolvedMode = isDarkMode ? "dark" : "light";
  const customTheme = useMemo(
    () => ({
      neutralColor,
      primaryColor: (primaryColor in COLOR_KEY_TO_HEX
        ? primaryColor
        : "geekblue") as PrimaryColors,
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
      <ThemeProvider
        key={`${primaryColor}-${resolvedMode}`}
        themeMode={resolvedMode}
        // Emotion global styles insert DOM nodes during hydration unless deferred.
        enableGlobalStyle={hydrated}
        customTheme={customTheme}
      >
        <ConfigProvider
          theme={{
            token: {
              colorPrimary: resolvePrimaryColor(primaryColor),
              colorInfo: resolvePrimaryColor(primaryColor),
            },
            cssVar: { key: "app" },
            algorithm: isDarkMode
              ? antTheme.darkAlgorithm
              : antTheme.defaultAlgorithm,
          }}
        >
          <App
            style={{
              minHeight: "inherit",
              width: "inherit",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {children}
          </App>
        </ConfigProvider>
      </ThemeProvider>
    </AppThemeContext.Provider>
  );
};
