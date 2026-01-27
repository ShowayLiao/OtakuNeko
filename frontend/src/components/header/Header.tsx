"use client";

import { Header as LobeHeader } from '@lobehub/ui';
import SearchBar from './SearchBar';
import { ThemeSwitcher } from '@/features/Theme/ThemeSwitcher';
import { ThemeModeSwitcher } from '@/features/Theme/ThemeModeSwitcher';
import User from './User';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { theme } from 'antd';

interface HeaderProps {
  className?: string;
}

export const Header: React.FC<HeaderProps> = ({ className = '' }) => {
  // 从 useAppTheme 获取的 primaryColor 现在始终是 HEX 值
  const { primaryColor } = useAppTheme();
  const { token } = theme.useToken();

  return (
    <div style={{ 
      // 使用 backdropFilter 增加磨砂玻璃效果 (可选)
      backdropFilter: 'saturate(180%) blur(10px)',
      background: `rgba(${parseInt(token.colorBgContainer.slice(1, 3), 16)}, ${parseInt(token.colorBgContainer.slice(3, 5), 16)}, ${parseInt(token.colorBgContainer.slice(5, 7), 16)}, 0.8)`,
      // 🔥 阴影
      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02)',
      borderBottom: `1px solid ${token.colorSplit}`, // 配合极细的边框效果更好
      zIndex: 50
    }}>
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
          {/* <SearchBar className="w-64" /> */}
          <User />
        </div>
      }
      
      nav={
        <div className="flex items-center gap-2">
          {/* 主题切换器已迁移到侧边栏 */}
        </div>
      }
    />
    </div>
  );
};