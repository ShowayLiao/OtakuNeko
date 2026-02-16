"use client";

import {Header} from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { SearchBar } from '@lobehub/ui';
import { Calendar } from 'lucide-react';
import { useState } from 'react';

interface TimetableHeaderProps {
  onSearch?: (value: string) => void;
  onViewModeChange?: (mode: 'grid' | 'list') => void;
}

export default function TimetableHeader({ 
  onSearch, 
  onViewModeChange
}: TimetableHeaderProps) {
  const { primaryColor } = useAppTheme();
  // 搜索框通常保留本地状态，用于处理输入时的即时显示，回车或防抖后再通知父组件
  const [searchKw, setSearchKw] = useState('');

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchKw(value);
    onSearch?.(value);
  };

  return (
    <div className="w-full">
      <Header
        leftArea={
          <div className="flex items-center gap-3">
            <Calendar size={20} style={{ color: primaryColor }} />
            <span className="text-xl font-bold font-sans tracking-tight" style={{ color: primaryColor }}>
              动画时间表
            </span>
          </div>
        }
        centerArea={
          <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ marginLeft: 'auto' }}>
              <SearchBar 
                placeholder="搜索时间表..." 
                enableShortKey 
                shortKey="k"
                value={searchKw}
                onChange={handleSearchChange}
                // 建议加上 allowClear 方便用户一键清除
                allowClear 
                style={{ width: 240 }}
              />
            </div>
          </div>
        }
      />
    </div>
  );
}