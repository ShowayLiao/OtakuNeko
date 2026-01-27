'use client';

import React, { useState } from 'react';
import { 
  Grid, 
  SearchBar, 
  Tabs, 
  ActionIcon, 
  Tag, 

  Empty 
} from '@lobehub/ui';
import { Spotlight } from '@lobehub/ui/awesome';
import { 
  LayoutGrid, 
  List, 
  Filter, 
  Tv, 
  Clapperboard, 
  BookOpen 
} from 'lucide-react';

// --- 1. 类型定义与模拟数据 ---
type MediaType = 'anime' | 'movie' | 'manga';

interface MediaItem {
  id: string;
  title: string;
  cover: string;
  type: MediaType;
  status: 'watching' | 'completed' | 'planned';
  score: number;
}

// 这里的图片仅作演示，实际请替换为你的数据源
const mockData: MediaItem[] = [
  { id: '1', title: '葬送的芙莉莲', type: 'anime', status: 'watching', score: 9.8, cover: 'https://cdn.myanimelist.net/images/anime/1015/138006l.jpg' },
  { id: '2', title: '奥本海默', type: 'movie', status: 'completed', score: 9.2, cover: 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg' },
  { id: '3', title: '电锯人', type: 'manga', status: 'completed', score: 8.9, cover: 'https://cdn.myanimelist.net/images/manga/3/216464l.jpg' },
  { id: '4', title: '赛博朋克：边缘行者', type: 'anime', status: 'completed', score: 9.5, cover: 'https://cdn.myanimelist.net/images/anime/1846/126432l.jpg' },
  { id: '5', title: '千与千寻', type: 'movie', status: 'completed', score: 9.6, cover: 'https://image.tmdb.org/t/p/w500/39wmItIWsg5sZMyRUKGk25sF5QP.jpg' },
];

export default function CollectionPage() {
  const [activeTab, setActiveTab] = useState('all');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchKw, setSearchKw] = useState('');

  // --- 2. 过滤逻辑 ---
  const filteredItems = mockData.filter(item => {
    const matchTab = activeTab === 'all' || item.type === activeTab;
    const matchSearch = item.title.toLowerCase().includes(searchKw.toLowerCase());
    return matchTab && matchSearch;
  });

  return (
    <div className="flex flex-col h-full gap-6">
      
      {/* --- 顶部区域：完全还原截图布局 --- */}
      <div className="flex flex-col gap-4">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">我的收藏</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              记录所见所爱，共 {mockData.length} 部作品
            </p>
          </div>
          
          <div className="flex gap-2">
            <SearchBar 
              placeholder="搜索 ACG 作品..." 
              enableShortKey 
              shortKey="k"
              value={searchKw}
              onChange={(e) => setSearchKw(e.target.value)}
              className="w-64" // 控制搜索框宽度
            />
            <ActionIcon icon={Filter} title="筛选" size="large" className="border border-slate-200 dark:border-slate-700 rounded-lg"/>
          </div>
        </div>

        {/* --- Tabs 与 视图切换 --- */}
        <div className="flex justify-between items-end border-b border-slate-200 dark:border-slate-800 pb-2">
          <Tabs
            items={[
              { key: 'all', label: '全部' },
              { key: 'anime', label: '动画', icon: <Tv size={16}/> },
              { key: 'movie', label: '电影', icon: <Clapperboard size={16}/> },
              { key: 'manga', label: '漫画', icon: <BookOpen size={16}/> },
            ]}
            activeKey={activeTab}
            onChange={setActiveTab}
          />
          
          <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg">
            <ActionIcon 
              icon={LayoutGrid} 
              active={viewMode === 'grid'} 
              onClick={() => setViewMode('grid')}
              size="small"
              title="网格视图"
            />
            <ActionIcon 
              icon={List} 
              active={viewMode === 'list'} 
              onClick={() => setViewMode('list')}
              size="small"
              title="列表视图"
            />
          </div>
        </div>
      </div>

      {/* --- 内容区域 --- */}
      <div className="flex-1 min-h-0"> 
        {filteredItems.length === 0 ? (
          <div className="flex h-64 items-center justify-center">
            <Empty description="没有找到相关内容" image="simple" />
          </div>
        ) : (
          /* 使用 Grid 组件，width={180} 会自动计算列数，适合响应式 */
          <Grid gap={20} width={180} >
            {filteredItems.map((item) => (
              <Spotlight key={item.id} className="rounded-xl h-full">
                <div 
                  className="group relative flex flex-col h-full bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden cursor-pointer hover:shadow-lg transition-all"
                  // 这里可以加 onClick 打开详情 Drawer
                >
                  {/* 封面图 (2:3 比例) */}
                  <div className="aspect-[2/3] w-full relative overflow-hidden bg-slate-100 dark:bg-slate-900">
                    <img 
                      src={item.cover} 
                      alt={item.title} 
                      className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-500"
                    />
                    {/* 右上角评分 */}
                    <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-sm text-white text-xs font-bold px-1.5 py-0.5 rounded flex items-center gap-1">
                      <span>★</span>{item.score}
                    </div>
                  </div>

                  {/* 信息 */}
                  <div className="p-3 flex flex-col flex-1 gap-2">
                    <h3 className="font-medium text-sm text-slate-900 dark:text-slate-100 line-clamp-2 leading-tight">
                      {item.title}
                    </h3>
                    
                    <div className="mt-auto flex items-center justify-between">
                      <Tag size="small" color={item.type === 'anime' ? 'blue' : item.type === 'movie' ? 'purple' : 'green'}>
                         {item.type.toUpperCase()}
                      </Tag>
                    </div>
                  </div>
                </div>
              </Spotlight>
            ))}
          </Grid>
        )}
      </div>
    </div>
  );
}