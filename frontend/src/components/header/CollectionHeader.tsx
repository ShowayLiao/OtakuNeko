"use client";

import {Header} from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { Segmented, SearchBar, ActionIcon, Icon } from '@lobehub/ui';
import { Bookmark, Film, Book, Gamepad2, Users, Filter, LayoutGrid } from 'lucide-react';
import { useState } from 'react';

interface CollectionHeaderProps {
  onSearch?: (value: string) => void;
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  
  // 🔥 核心：接收父组件传来的当前筛选值
  filterValue: string;
  // 🔥 核心：通知父组件改变筛选值
  onFilterChange: (value: string) => void;
}

export default function CollectionHeader({ 
  onSearch, 
  onViewModeChange, 
  filterValue, 
  onFilterChange 
}: CollectionHeaderProps) {
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
            <Bookmark size={20} style={{ color: primaryColor }} />
            <span className="text-xl font-bold font-sans tracking-tight" style={{ color: primaryColor }}>
              我的收藏
            </span>
          </div>
        }
        centerArea={
          <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              
              {/* --- 筛选器核心组件 --- */}
              <Segmented
                // 🔥 1. 绑定父组件传下来的值 (受控)
                value={filterValue} 
                
                // 🔥 2. 类型断言修复报错
                onChange={(value) => {
                  onFilterChange?.(value as string); 
                }}
                
                options={[
                  {
                    icon: <Icon icon={LayoutGrid} />,
                    label: '全部',
                    value: 'all',
                  },
                  {
                    icon: <Icon icon={Film} />,
                    label: '动画',
                    value: 'anime',
                  },
                  {
                    icon: <Icon icon={Book} />,
                    label: '书籍',
                    value: 'books', // 注意：这里传出去的是 'books'，page.tsx 里记得映射到 'manga'
                  },
                  {
                    icon: <Icon icon={Gamepad2} />,
                    label: '游戏',
                    value: 'games',
                  },
                  {
                    icon: <Icon icon={Users} />,
                    label: '三次元',
                    value: 'real',
                  },
                ]}
              />
              
              
            </div>
            
            {/* --- 状态筛选组件 --- */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Segmented
                options={[
                  {
                    label: '全部',
                    value: 'all',
                  },
                  {
                    label: '在看',
                    value: 'watching',
                  },
                  {
                    label: '想看',
                    value: 'planned',
                  },
                  {
                    label: '搁置',
                    value: 'on_hold',
                  },
                  {
                    label: '已看',
                    value: 'completed',
                  },
                ]}
              />
              <ActionIcon 
                icon={Filter} 
                title="高级筛选" 
                size="large" 
                className="border border-slate-200 dark:border-slate-700 rounded-lg"
              />
            </div>
            
            <div style={{ marginLeft: 'auto' }}>
              <SearchBar 
                placeholder="搜索 ACG 作品..." 
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