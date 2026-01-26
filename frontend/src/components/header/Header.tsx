"use client";

import { Header as LobeHeader } from '@lobehub/ui';
import SearchBar from './SearchBar';
import { ThemeSwitcher } from '@/features/Theme/ThemeSwitcher';
import { ThemeModeSwitcher } from '@/features/Theme/ThemeModeSwitcher';
import User from './User';
import { useAppTheme } from '@/components/providers/LobeProvider';

interface HeaderProps {
  className?: string;
}

export const Header: React.FC<HeaderProps> = ({ className = '' }) => {
  // 从 useAppTheme 获取的 primaryColor 现在始终是 HEX 值
  const { primaryColor } = useAppTheme();

  return (
    <LobeHeader
      className={className}
      logo={
        <div className="flex items-center gap-3 px-2">
          <img 
            src="/Icon.png" 
            alt="OtakuNeko Logo" 
            className="h-8 w-8 object-contain" 
          />
          <span className="text-xl font-bold font-sans tracking-tight" style={{ color: primaryColor }}>
            OtakuNeko
          </span>
        </div>
      }
      actions={
        <div className="flex items-center gap-2">
          <SearchBar className="w-64" />
          <User />
        </div>
      }
      
      nav={
        <div className="flex items-center gap-2">
          <ThemeSwitcher />
          <ThemeModeSwitcher />
        </div>
      }
    />
  );
};