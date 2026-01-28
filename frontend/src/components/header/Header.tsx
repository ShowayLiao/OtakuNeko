"use client";

import SearchBar from './SearchBar';
import User from './User';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { theme } from 'antd';

interface HeaderProps {
  leftArea?: React.ReactNode;
  centerArea?: React.ReactNode;
  className?: string;
}

export const Header: React.FC<HeaderProps> = ({ leftArea, centerArea, className = '' }) => {
  const { primaryColor } = useAppTheme();
  const { token } = theme.useToken();

  return (
    <div className={`h-16 flex items-center justify-between px-4 border-b border-gray-100 dark:border-gray-800 bg-white/50 backdrop-blur-md ${className}`} style={{ 
      borderBottom: `1px solid ${token.colorSplit}`,
      background: `rgba(${parseInt(token.colorBgContainer.slice(1, 3), 16)}, ${parseInt(token.colorBgContainer.slice(3, 5), 16)}, ${parseInt(token.colorBgContainer.slice(5, 7), 16)}, 0.8)`,
      backdropFilter: 'saturate(180%) blur(10px)',
      zIndex: 50
    }}>
      
      {/* 左侧：可变区域 (插槽) */}
      <div className="flex items-center gap-3 w-48">
        {leftArea}
      </div>

      {/* 中间：可变区域 (插槽) */}
      <div className="flex-1 flex justify-center">
        {centerArea}
      </div>

      {/* 右侧：永远存在的头像/设置 */}
      <div className="flex items-center justify-end gap-2 w-48">
        {/* <SearchBar className="w-64" /> */}
        <User />
      </div>
    </div>
  );
};