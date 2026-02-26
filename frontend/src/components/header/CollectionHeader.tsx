"use client";

import {Header} from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { Segmented, ActionIcon, Icon } from '@lobehub/ui';
import SearchBar from './SearchBar';
import { Bookmark, Film, Book, Gamepad2, Users, Filter, LayoutGrid } from 'lucide-react';
import { useState } from 'react';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';

interface CollectionHeaderProps {
  onSearch?: (value: string) => void;
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  
  // 🔥 核心：接收父组件传来的当前筛选值
  filterValue: string;
  // 🔥 核心：通知父组件改变筛选值
  onFilterChange: (value: string) => void;
  
  // 状态筛选相关
  statusValue?: string;
  onStatusChange?: (value: string) => void;
  
  // 排序相关
  onSortChange?: (value: string) => void;
}

export default function CollectionHeader({ 
  onSearch, 
  onViewModeChange, 
  filterValue, 
  onFilterChange,
  statusValue = 'all',
  onStatusChange,
  onSortChange
}: CollectionHeaderProps) {
  const { primaryColor } = useAppTheme();
  // 搜索框使用SearchBar组件内部的状态管理和防抖功能

  // 排序选项配置
  const sortOptions = [
    { value: 'updated_at', label: '更新时间' },
    { value: 'rate', label: '用户评分' },
    { value: 'score', label: '网站得分' },
    { value: 'date', label: '日期' },
  ];

  // 排序菜单配置
  const items: MenuProps['items'] = sortOptions.map((option) => ({
    key: option.value,
    label: option.label,
    onClick: () => {
      onSortChange?.(option.value);
    },
  }));

  // 菜单项点击处理函数
  const handleMenuClick: MenuProps['onClick'] = (e) => {
    onSortChange?.(e.key);
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
                value={statusValue}
                onChange={(value) => {
                  onStatusChange?.(value as string);
                }}
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
              <Dropdown 
                menu={{ 
                  items, 
                  onClick: handleMenuClick,
                  title: "排序方式"
                }} 
                trigger={['click']}
              >
                <button 
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '40px',
                    height: '40px',
                    borderRadius: '8px',
                    border: '1px solid var(--lobe-color-border)',
                    background: 'var(--lobe-color-bg-container)',
                    color: 'var(--lobe-color-text-primary)',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  title="排序方式"
                >
                  <Filter size={18} />
                </button>
              </Dropdown>
            </div>
            
            <div style={{ marginLeft: 'auto' }}>
              <SearchBar 
                placeholder="搜索 ACG 作品..." 
                enableShortKey 
                shortKey="k"
                onSearch={onSearch}
                debounceDelay={500}
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