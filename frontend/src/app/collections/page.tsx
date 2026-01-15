"use client";

import { useCallback, useState } from 'react';
import Image from 'next/image';
import { Search, Clock, Star, TrendingUp, Calendar } from 'lucide-react';
import { SortDropdown } from '@/components/features/SortDropdown';
import { PageLayout } from '@/components/layout/PageLayout';
import { LoadingState } from '@/components/state/LoadingState';
import { ErrorState } from '@/components/state/ErrorState';
import { GenericEmptyState } from '@/components/state/GenericEmptyState';
import { FloatingActionButton } from '@/components/features/FloatingActionButton';
import { Badge } from '@/components/ui/Badge';
import { useCollection } from '@/hooks/useCollection';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('CollectionGridPage');

export interface CollectionItem {
  id: number;
  title: string;
  posterUrl: string;
  rating: number;
  status: string;
  updated_at: string;
  type?: 'anime' | 'game' | 'book';
}

export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

export interface CollectionGridPageProps {
  items?: CollectionItem[];
  onAddItem?: () => void;
  onItemClick?: (item: CollectionItem) => void;
  fetchItems?: () => Promise<CollectionItem[]>;
  className?: string;
}

const CollectionGridPage = ({
  onAddItem,
  onItemClick,
  fetchItems,
  className
}: CollectionGridPageProps) => {
  const {
    filteredItems,
    loadingState,
    error,
    activeFilter,
    handleFilter,
    handleRetry
  } = useCollection({
    fetchItems,
    autoFetch: !!fetchItems
  });

  const [sortValue, setSortValue] = useState('recent');
  const [activeTypeFilter, setActiveTypeFilter] = useState('全部');
  const [activeStatusFilter, setActiveStatusFilter] = useState('全部状态');

  const typeFilters = ['全部','动画', '书籍', '游戏', '剧集'];
  const statusFilters = ['全部状态','在看/玩', '搁置', '追/玩完'];

  const sortOptions = [
    { label: '最近更新', value: 'recent', icon: <Clock className="w-4 h-4" /> },
    { label: '我的评分（高到低）', value: 'rating-desc', icon: <Star className="w-4 h-4" /> },
    { label: '大众评分（高到低）', value: 'public-rating-desc', icon: <TrendingUp className="w-4 h-4" /> },
    { label: '添加时间', value: 'added', icon: <Calendar className="w-4 h-4" /> }
  ];

  const handleAddItem = useCallback(() => {
    logger.info('handleAddItem', 'Add item button clicked');
    onAddItem?.();
  }, [onAddItem]);

  const handleItemClick = useCallback((item: CollectionItem) => {
    logger.info('handleItemClick', 'Item clicked', { id: item.id, title: item.title });
    onItemClick?.(item);
  }, [onItemClick]);

  const handleFilterChange = useCallback((filter: string, filterType: 'type' | 'status') => {
    if (filterType === 'type') {
      setActiveTypeFilter(filter);
    } else {
      setActiveStatusFilter(filter);
    }
    handleFilter(filter);
    logger.debug('handleFilterChange', 'Filter changed', { filter, filterType });
  }, [handleFilter]);

  return (
    <div className={cn("min-h-screen bg-background p-4 md:p-8", className)}>
      <PageLayout maxWidth="full" padding="none">
        <div className="mb-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 md:gap-4">
            <div className="flex flex-row items-center gap-4 md:gap-6">
              <div>
                <div className="flex flex-wrap gap-2 md:gap-3">
                    {typeFilters.map((filter) => (
                      <button
                        key={filter}
                        className={cn(
                          "px-4 md:px-5 py-2 md:py-2.5 rounded-full font-medium text-sm transition-all duration-300",
                          "focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2",
                          "relative overflow-hidden",
                          activeTypeFilter === filter
                            ? 'bg-primary text-white shadow-lg shadow-primary/30 scale-105'
                            : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 hover:scale-105'
                        )}
                        onClick={() => handleFilterChange(filter, 'type')}
                        aria-pressed={activeTypeFilter === filter}
                        aria-label={`筛选类型: ${filter}`}
                      >
                        {filter}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="w-px h-8 bg-gray-300 dark:bg-gray-600 flex-shrink-0" />

                <div>
                  <div className="flex flex-wrap gap-2 md:gap-3">
                    {statusFilters.map((filter) => (
                      <button
                        key={filter}
                        className={cn(
                          "px-4 md:px-5 py-2 md:py-2.5 rounded-full font-medium text-sm transition-all duration-300",
                          "focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2",
                          "relative overflow-hidden",
                          activeStatusFilter === filter
                            ? 'bg-primary text-white shadow-lg shadow-primary/30 scale-105'
                            : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 hover:scale-105'
                        )}
                        onClick={() => handleFilterChange(filter, 'status')}
                        aria-pressed={activeStatusFilter === filter}
                        aria-label={`筛选状态: ${filter}`}
                      >
                        {filter}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

            <SortDropdown
              value={sortValue}
              onChange={setSortValue}
              options={sortOptions}
              ariaLabel="排序选项"
            />
          </div>
        </div>

        {loadingState === 'loading' && (
          <LoadingState message="加载中..." size="lg" />
        )}

        {loadingState === 'error' && (
          <ErrorState
            title="加载失败"
            message={error || '无法加载收藏数据，请稍后重试'}
            onRetry={handleRetry}
          />
        )}

        {loadingState === 'success' && filteredItems.length === 0 && (
          <GenericEmptyState
            title={activeFilter !== '全部' ? '未找到匹配的收藏' : '暂无收藏'}
            description={activeFilter !== '全部'
              ? '尝试调整筛选条件'
              : '点击右下角的添加按钮开始添加您的第一个收藏'}
            icon={<Search className="w-16 h-16 text-gray-400" />}
            actionLabel="添加收藏"
            onAction={handleAddItem}
          />
        )}

        {loadingState === 'success' && filteredItems.length > 0 && (
          <div 
            className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 md:gap-6 lg:gap-8"
            role="list"
            aria-label="收藏列表"
          >
            {filteredItems.map((item, index) => (
              <div
                key={item.id}
                className="group relative aspect-[2/3] rounded-lg overflow-hidden cursor-pointer bg-gray-200 dark:bg-gray-800"
                onClick={() => handleItemClick(item)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleItemClick(item);
                  }
                }}
                role="listitem"
                tabIndex={0}
                aria-label={`${item.title}, 评分: ${item.rating}, 状态: ${item.status}`}
              >
                <div className="absolute inset-0 overflow-hidden">
                  <Image
                    src={item.posterUrl}
                    alt={item.title}
                    fill
                    sizes="(max-width: 640px) 50vw, (max-width: 768px) 33vw, (max-width: 1024px) 25vw, (max-width: 1280px) 20vw, 16vw"
                    className="object-cover transition-all duration-500 group-hover:scale-110 group-hover:brightness-75"
                    loading={index < 6 ? 'eager' : 'lazy'}
                    unoptimized
                  />
                </div>

                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/50 to-transparent p-3 md:p-4 transform translate-y-full group-hover:translate-y-0 group-focus:translate-y-0 transition-transform duration-300">
                  <h3 className="text-white font-semibold text-sm md:text-base mb-1 line-clamp-2">
                    {item.title}
                  </h3>
                  <div className="flex items-center justify-between">
                    <span className="text-yellow-300 flex items-center text-sm" aria-label={`评分: ${item.rating}`}>
                      <span className="mr-1" aria-hidden="true">⭐</span>
                      {item.rating}
                    </span>
                    <Badge
                      variant="default"
                      className="bg-primary/80 text-white border-0 text-xs"
                      showDot={false}
                      aria-label={`状态: ${item.status}`}
                    >
                      {item.status}
                    </Badge>
                  </div>
                </div>

                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity duration-300 pointer-events-none">
                  <div className="w-12 h-12 md:w-16 md:h-16 rounded-full bg-primary/90 flex items-center justify-center text-white transition-all duration-200 scale-100 group-hover:scale-110">
                    <svg className="w-6 h-6 md:w-8 md:h-8" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                    </svg>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </PageLayout>

      <FloatingActionButton />
    </div>
  );
};

export default CollectionGridPage;
