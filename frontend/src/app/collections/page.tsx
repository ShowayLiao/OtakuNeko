"use client";

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Header } from '@/components/layout/Header';

// 定义收藏项类型
interface CollectionItem {
  id: number;
  title: string;
  posterUrl: string;
  rating: number;
  status: string;
}

export default function CollectionsPage() {
  // 模拟数据
  const [collectionItems, setCollectionItems] = useState<CollectionItem[]>([
    {
      id: 1,
      title: '进击的巨人',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Attack+on+Titan',
      rating: 9.2,
      status: '已追完'
    },
    {
      id: 2,
      title: '鬼灭之刃',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Demon+Slayer',
      rating: 9.1,
      status: '在看'
    },
    {
      id: 3,
      title: '海贼王',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=One+Piece',
      rating: 9.5,
      status: '在看'
    },
    {
      id: 4,
      title: '火影忍者',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Naruto',
      rating: 9.0,
      status: '已追完'
    },
    {
      id: 5,
      title: '东京食尸鬼',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Tokyo+Ghoul',
      rating: 8.5,
      status: '已追完'
    },
    {
      id: 6,
      title: '我的英雄学院',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=My+Hero+Academia',
      rating: 8.8,
      status: '在看'
    },
    {
      id: 7,
      title: '一拳超人',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=One-Punch+Man',
      rating: 9.3,
      status: '已追完'
    },
    {
      id: 8,
      title: '灵笼',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Ling+Long',
      rating: 8.7,
      status: '已追完'
    },
    {
      id: 9,
      title: '原神',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Genshin+Impact',
      rating: 9.4,
      status: '在玩'
    },
    {
      id: 10,
      title: '塞尔达传说',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Zelda',
      rating: 9.6,
      status: '已通关'
    },
    {
      id: 11,
      title: '最终幻想VII',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=FFVII',
      rating: 9.2,
      status: '已通关'
    },
    {
      id: 12,
      title: '王国之心',
      posterUrl: 'https://placehold.co/400x600/FF6600/FFFFFF?text=Kingdom+Hearts',
      rating: 8.9,
      status: '在玩'
    }
  ]);

  // 筛选状态
  const [activeFilter, setActiveFilter] = useState('全部');
  const filters = ['全部', '动画', '游戏', '书籍', '已追完', '在看', '在玩'];

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* 全局Header */}
      <Header />

      {/* 内容区域 */}
      <main className="flex-1 p-4 lg:p-6 overflow-y-auto">
        {/* 筛选栏 */}
        <div className="flex flex-wrap gap-3 mb-10">
          {filters.map((filter) => (
            <button
              key={filter}
              className={`px-4 py-2 rounded-full font-medium transition-all duration-200 ${activeFilter === filter ? 'bg-primary text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}
              onClick={() => setActiveFilter(filter)}
            >
              {filter}
            </button>
          ))}
        </div>

        {/* 响应式网格布局 */}
        <div className="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-8">
          {collectionItems.map((item) => (
            <div
              key={item.id}
              className="group relative aspect-[2/3] rounded-lg overflow-hidden cursor-pointer"
            >
              {/* 海报图片 */}
              <div className="absolute inset-0 overflow-hidden">
                <img
                  src={item.posterUrl}
                  alt={item.title}
                  className="w-full h-full object-cover transition-all duration-500 group-hover:scale-110 group-hover:brightness-75"
                />
              </div>

              {/* 底部信息层 */}
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-4 transform translate-y-full group-hover:translate-y-0 transition-transform duration-300">
                <h3 className="text-white font-semibold mb-1">{item.title}</h3>
                <div className="flex items-center justify-between">
                  <span className="text-yellow-300 flex items-center">
                    ⭐ {item.rating}
                  </span>
                  <span className="text-white bg-primary/80 px-2 py-0.5 rounded text-xs">
                    {item.status}
                  </span>
                </div>
              </div>

              {/* 中心播放/详情按钮 */}
              <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                <button className="w-16 h-16 rounded-full bg-primary/90 flex items-center justify-center text-white hover:bg-primary transition-all duration-200 scale-100 group-hover:scale-110">
                  <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      {/* 右下角悬浮按钮 */}
      <button className="fixed bottom-8 right-8 w-14 h-14 rounded-full bg-primary text-white shadow-lg hover:-translate-y-1 transition-all duration-200 flex items-center justify-center">
        <Plus className="w-6 h-6" />
      </button>
    </div>
  );
}