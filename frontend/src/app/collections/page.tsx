'use client';

import React, { useState } from 'react';
import CollectionHeader from '@/components/header/CollectionHeader';
import CollectionContent from '@/components/collection/CollectionContent';

// --- 类型定义与模拟数据 ---
type MediaType = 'anime' | 'movie' | 'manga';

interface MediaItem {
  id: string;
  title: string;
  cover: string;
  type: MediaType;
  status: 'watching' | 'completed' | 'planned';
  score: number;
  eps?: number; // 补充定义
}

// 模拟数据
const mockData: MediaItem[] = [
  { id: '1', title: '葬送的芙莉莲', type: 'anime', status: 'watching', score: 9.8, cover: 'https://cdn.myanimelist.net/images/anime/1015/138006l.jpg', eps: 28 },
  { id: '2', title: '奥本海默', type: 'movie', status: 'completed', score: 9.2, cover: 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg' },
  { id: '3', title: '电锯人', type: 'manga', status: 'completed', score: 8.9, cover: 'https://cdn.myanimelist.net/images/manga/3/216464l.jpg' },
  { id: '4', title: '赛博朋克：边缘行者', type: 'anime', status: 'completed', score: 9.5, cover: 'https://cdn.myanimelist.net/images/anime/1846/126432l.jpg', eps: 10 },
  { id: '5', title: '千与千寻', type: 'movie', status: 'completed', score: 9.6, cover: 'https://image.tmdb.org/t/p/w500/39wmItIWsg5sZMyRUKGk25sF5QP.jpg' },
];

export default function CollectionPage() {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchKw, setSearchKw] = useState('');
  // 对应 Header 里 Segmented 的 value: 'all' | 'anime' | 'books' | 'games' | 'real'
  const [filterValue, setFilterValue] = useState('all'); 

  // 逻辑处理：过滤数据
  const filteredItems = mockData.filter(item => {
    // 1. 搜索过滤
    const matchesSearch = item.title.toLowerCase().includes(searchKw.toLowerCase());
    
    // 2. 筛选过滤 (注意：这里需要把 UI 的 value 映射到数据的 type)
    let matchesFilter = true;
    if (filterValue !== 'all') {
      if (filterValue === 'books') {
         // UI叫 books，数据叫 manga
         matchesFilter = item.type === 'manga'; 
      } else if (filterValue === 'anime') {
         // UI叫 anime，数据里可能是 anime 或 movie (或者你可以拆分 movie)
         matchesFilter = item.type === 'anime';
      } else if (filterValue === 'real') {
         matchesFilter = item.type === 'movie'; // 假设三次元对应 movie
      } else {
         // 其他情况直接匹配
         matchesFilter = item.type === (filterValue as MediaType);
      }
    }
    
    return matchesSearch && matchesFilter;
  });

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-50 dark:bg-neutral-900">
      
      {/* 顶部 Header */}
      <div className="flex-none bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-800 z-10">
         <CollectionHeader 
            onSearch={setSearchKw}
            onViewModeChange={setViewMode}
            
            // 🔥 必须把这两行都加上！
            // filterValue 告诉组件“现在该亮哪个按钮”
            filterValue={filterValue} 
            // onFilterChange 告诉父组件“用户点了哪个按钮”
            onFilterChange={setFilterValue}
         />
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto">
         <CollectionContent items={filteredItems} />
      </div>
      
    </div>
  )
}