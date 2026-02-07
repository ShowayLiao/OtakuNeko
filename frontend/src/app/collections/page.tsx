'use client';

import React, { useState, useEffect } from 'react';
import CollectionHeader from '@/components/header/CollectionHeader';
import CollectionContent from '@/components/collection/CollectionContent';
import { collectionService, CollectionItem } from '@/services/collections';

export default function CollectionPage() {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchKw, setSearchKw] = useState('');
  // 对应 Header 里 Segmented 的 value: 'all' | 'anime' | 'books' | 'games' | 'real'
  const [filterValue, setFilterValue] = useState('all'); 
  // 状态筛选值: 'all' | 'watching' | 'planned' | 'on_hold' | 'completed'
  const [statusValue, setStatusValue] = useState('all');
  const [sortBy, setSortBy] = useState('updated_at');
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 映射 UI 筛选值到后端 subject_type
  const mapFilterToSubjectType = (filter: string): number | undefined => {
    switch (filter) {
      case 'books':
        return 1; // 书籍
      case 'anime':
        return 2; // 动画
      case 'games':
        return 4; // 游戏
      case 'real':
        return 6; // 三次元
      default:
        return undefined;
    }
  };

  // 映射 UI 状态值到后端 CollectionStatus 枚举值
  const mapStatusToCollectionStatus = (status: string): number | undefined => {
    switch (status) {
      case 'watching':
        return 3; // DO (在看)
      case 'planned':
        return 1; // WISH (想看)
      case 'on_hold':
        return 4; // ON_HOLD (搁置)
      case 'completed':
        return 2; // COLLECT (看过)
      default:
        return undefined;
    }
  };

  // 获取收藏数据
  const fetchCollections = async () => {
    setLoading(true);
    setError(null);
    try {
      const subject_type = mapFilterToSubjectType(filterValue);
      const status = mapStatusToCollectionStatus(statusValue);
      const response = await collectionService.getCollections({
        subject_type,
        keyword: searchKw,
        limit: 100,
        sort_by: sortBy,
        status: status || undefined,
      });
      setItems(response.items);
    } catch (err) {
      setError('获取收藏列表失败，请稍后重试');
      console.error('Error fetching collections:', err);
    } finally {
      setLoading(false);
    }
  };

  // 当搜索关键词、筛选条件、状态或排序方式变化时，重新获取数据
  useEffect(() => {
    fetchCollections();
  }, [searchKw, filterValue, statusValue, sortBy]);

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
            
            // 状态筛选相关
            statusValue={statusValue}
            onStatusChange={setStatusValue}
            
            // 排序变化回调
            onSortChange={setSortBy}
         />
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-red-500">
            {error}
          </div>
        ) : (
          <CollectionContent items={items} />
        )}
      </div>
      
    </div>
  )
}