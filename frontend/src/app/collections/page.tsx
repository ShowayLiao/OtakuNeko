"use client";

import { useState, useEffect, useMemo, useRef } from 'react';
import { Plus, X, UploadCloud, PenLine, Loader2 } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { useInView } from 'react-intersection-observer';
import { PosterCard } from '@/components/PosterCard';
import { SortDropdown } from '@/components/SortDropdown';
import { DoubanImportDialog } from '@/components/DoubanImportDialog';
import { GridImportModal } from '@/components/settings/GridImportModal';
import { useManualAddDialogStore } from '@/lib/manualAddDialogStore';
import { useSync } from '@/hooks/useSync';

// 定义后端返回的Subject类型
interface BackendSubject {
  id: number;
  source_id: string;
  name: string;
  name_cn: string;
  cover_url: string;
  type: number;
  eps: number;
  score: number;
  tags: string[];
  images?: {
    large: string;
    common: string;
    medium: string;
    small: string;
    grid: string;
  };
}

// 定义后端返回的收藏项类型
interface BackendCollectionItem {
  id: number;
  updated_at: string;
  status: string;
  subject: BackendSubject;
}

// 定义前端使用的收藏项类型
interface CollectionItem {
  // --- 原始 Bangumi 数据 ---
  id: number;
  source_id: string;
  name_cn: string;
  name: string;
  cover_url: string;
  score: number;
  type: number; // 1=书籍, 2=动画, 3=音乐, 4=游戏, 6=剧集
  tags: string[];
  eps: number;
  images?: {
    large: string;
    common: string;
    medium: string;
    small: string;
    grid: string;
  };
  // --- 本地数据库附加字段 ---
  status: 'watching' | 'completed' | 'plan' | 'on_hold' | 'dropped' | 'unknown';
  updated_at: string; // ISO 时间字符串
}

// 定义API响应类型
interface CollectionApiResponse {
  total: number;
  items: BackendCollectionItem[];
}

export default function CollectionsPage() {
  const { openDialog: openManualAddDialog } = useManualAddDialogStore();
  
  const [showGridModal, setShowGridModal] = useState(false);
  
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [filterType, setFilterType] = useState<number | 'all'>('all'); // 1=书籍, 2=动画, 3=音乐, 4=游戏
  const [filterStatus, setFilterStatus] = useState<'all' | 'watching' | 'completed' | 'plan' | 'on_hold' | 'dropped'>('all');
  const [sortBy, setSortBy] = useState<'updated_at' | 'rate' | 'score' | 'date'>('updated_at'); // 排序方式
  const [isImportDialogOpen, setIsImportDialogOpen] = useState(false); // 豆瓣导入对话框状态
  const [isSpeedDialOpen, setIsSpeedDialOpen] = useState(false); // Speed Dial菜单状态
  const fabRef = useRef<HTMLDivElement>(null); // FAB容器引用
  
  // 使用全局同步状态
  const { isSyncing, handleSync } = useSync();
  
  // Intersection Observer for infinite scroll
  const { ref, inView } = useInView({
    threshold: 0.5,
    triggerOnce: false,
    rootMargin: '200px',
  });

  // 刷新数据的函数
  const refreshData = () => {
    setIsLoading(true);
    setItems([]);
    setOffset(0);
    setHasMore(true);
    fetchData(false);
  };

  // 监听来自 Header 的刷新事件
  useEffect(() => {
    const handleRefresh = () => {
      refreshData();
    };

    window.addEventListener('refreshCollections', handleRefresh);

    return () => {
      window.removeEventListener('refreshCollections', handleRefresh);
    };
  }, [refreshData]);

  // 获取数据的函数
  const fetchData = async (isLoadMore = false) => {
    const currentOffset = isLoadMore ? offset : 0;
    const limit = 20;
    
    try {
      // 构建请求URL，包含筛选条件、排序和分页参数
      const url = new URL('/api/collections', window.location.origin);
      if (filterType !== 'all') url.searchParams.append('subject_type', filterType.toString());
      if (filterStatus !== 'all') url.searchParams.append('status', filterStatus);
      url.searchParams.append('sort_by', sortBy);
      url.searchParams.append('offset', currentOffset.toString());
      url.searchParams.append('limit', limit.toString());
      
      const res = await fetch(url.toString());
      const data: CollectionApiResponse = await res.json();
      
      // 转换后端返回的数据结构
        if (data && Array.isArray(data.items)) {
          const transformedItems = data.items.map(item => ({
            id: item.id,
            source_id: item.subject?.source_id || item.id.toString(),
            name_cn: item.subject?.name_cn || '',
            name: item.subject?.name || '',
            cover_url: item.subject?.cover_url || '',
            score: item.subject?.score || 0,
            type: item.subject?.type || 0,
            tags: item.subject?.tags || [],
            eps: item.subject?.eps || 0,
            images: item.subject?.images,
            status: item.status as 'watching' | 'completed' | 'plan' | 'dropped' | 'unknown',
            updated_at: item.updated_at
          }));
        
        if (isLoadMore) {
          // 加载更多：追加新数据，并进行去重保护
          setItems(prev => {
            const newItems = transformedItems.filter(item => !prev.some(p => p.id === item.id));
            return [...prev, ...newItems];
          });
          setOffset(prev => prev + limit);
        } else {
          // 初始加载或筛选切换：替换数据
          setItems(transformedItems);
          setOffset(limit);
        }
        
        // 判断是否还有更多数据
        setHasMore(data.items.length >= limit);
      } else {
        if (!isLoadMore) {
          setItems([]);
        }
        setHasMore(false);
      }
    } catch (err) {
      console.error('Fetch failed:', err);
      
      // 出错时使用模拟数据作为 fallback
      if (!isLoadMore) {
        setItems([
          {
            id: 1,
            source_id: '5684',
            name_cn: '进击的巨人',
            name: 'Shingeki no Kyojin',
            cover_url: `https://picsum.photos/seed/${1}/300/450`,
            score: 9.2,
            type: 2,
            tags: ['科幻', '战斗', '热血', '机甲'],
            eps: 75,
            status: 'completed',
            updated_at: '2024-01-15T10:30:00Z'
          },
          {
            id: 2,
            source_id: '269087',
            name_cn: '鬼灭之刃',
            name: 'Kimetsu no Yaiba',
            cover_url: `https://picsum.photos/seed/${2}/300/450`,
            score: 9.1,
            type: 2,
            tags: ['奇幻', '战斗', '冒险'],
            eps: 54,
            status: 'completed',
            updated_at: '2024-01-16T14:20:00Z'
          },
          {
            id: 5,
            source_id: '269087',
            name_cn: '原神',
            name: 'Genshin Impact',
            cover_url: `https://picsum.photos/seed/${5}/300/450`,
            score: 9.4,
            type: 4,
            tags: ['冒险', '开放世界', '奇幻', '角色扮演'],
            eps: 0,
            status: 'watching',
            updated_at: '2024-01-19T11:20:00Z'
          },
          {
            id: 7,
            source_id: '3130',
            name_cn: '哈利·波特与魔法石',
            name: 'Harry Potter and the Philosopher\'s Stone',
            cover_url: `https://picsum.photos/seed/${7}/300/450`,
            score: 9.2,
            type: 1,
            tags: ['奇幻', '冒险', '魔法'],
            eps: 0,
            status: 'completed',
            updated_at: '2024-01-21T08:30:00Z'
          }
        ]);
        setHasMore(false);
      }
    } finally {
      if (isLoadMore) {
        setIsLoadingMore(false);
      } else {
        setIsLoading(false);
      }
    }
  };

  // 初始加载和筛选切换时的效果
  useEffect(() => {
    // 重置状态
    setIsLoading(true);
    setItems([]);
    setOffset(0);
    setHasMore(true);
    
    // 发起请求
    fetchData(false);
  }, [filterType, filterStatus, sortBy]);

  // 无限滚动的效果
  useEffect(() => {
    if (inView && hasMore && !isLoading && !isLoadingMore) {
      setIsLoadingMore(true);
      fetchData(true);
    }
  }, [inView, hasMore, isLoading, isLoadingMore]);

  // 点击菜单外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (fabRef.current && !fabRef.current.contains(event.target as Node)) {
        setIsSpeedDialOpen(false);
      }
    };

    if (isSpeedDialOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isSpeedDialOpen]);

  // 筛选逻辑
  const displayItems = useMemo(() => {
    let filteredItems = [...items];

    // 按类型筛选
    if (filterType !== 'all') {
      filteredItems = filteredItems.filter(item => item.type === filterType);
    }

    // 按状态筛选
    if (filterStatus !== 'all') {
      filteredItems = filteredItems.filter(item => item.status === filterStatus);
    }

    // 不再进行本地排序，完全信任后端返回的顺序
    return filteredItems;
  }, [items, filterType, filterStatus]);

  // 筛选按钮配置
  const typeFilters = [
    { label: '全部', value: 'all' },
    { label: '动画', value: 2 },
    { label: '游戏', value: 4 },
    { label: '书籍', value: 1 },
    { label: '剧集', value: 6 }
  ];

  const statusFilters = [
    { label: '全部状态', value: 'all' },
    { label: '在看', value: 'watching' },
    { label: '已追完', value: 'completed' },
    { label: '想看', value: 'plan' },
    { label: '搁置', value: 'on_hold' }
  ];

  // 排序选项配置
  const sortOptions = [
    { label: '🕒 最近加入 (默认)', value: 'updated_at' },
    { label: '⭐ 我的评分 (高到低)', value: 'rate' },
    { label: '🌟 大众评分 (高到低)', value: 'score' },
    { label: '📅 首播日期 (新到旧)', value: 'date' },
  ];

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* 全局Header */}
      <Header />

      {/* 内容区域 */}
      <main className="flex-1 p-4 lg:p-6 overflow-y-auto">
        {/* 筛选栏 */}
        <div className="flex flex-wrap gap-3 mb-10">
          {/* 类型筛选 */}
          {typeFilters.map((filter) => (
            <button
              key={filter.value}
              className={`px-4 py-2 rounded-full font-medium transition-all duration-200 ${filterType === filter.value ? 'bg-primary text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}
              onClick={() => setFilterType(filter.value as number | 'all')}
            >
              {filter.label}
            </button>
          ))}
          
          {/* 状态筛选 */}
          <div className="ml-4 hidden md:block">
            <span className="mr-2 text-gray-700 font-medium">状态：</span>
            {statusFilters.map((filter) => (
              <button
                key={filter.value}
                className={`px-4 py-2 rounded-full font-medium transition-all duration-200 ${filterStatus === filter.value ? 'bg-primary text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}
                onClick={() => setFilterStatus(filter.value as 'watching' | 'completed' | 'plan' | 'on_hold' | 'dropped' | 'all')}
              >
                {filter.label}
              </button>
            ))}
          </div>
          
          {/* 排序下拉菜单 */}
          <div className="ml-auto">
            <SortDropdown
              value={sortBy}
              onChange={(value) => setSortBy(value as 'updated_at' | 'rate' | 'score' | 'date')}
              options={sortOptions}
            />
          </div>
        </div>

        {/* 加载状态 */}
        {isLoading ? (
          <div className="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-8">
            {[...Array(12)].map((_, index) => (
              <div key={index} className="aspect-[2/3] rounded-lg bg-gray-200 animate-pulse"></div>
            ))}
          </div>
        ) : (
          <>
            {/* 空状态处理 */}
            {items.length === 0 ? (
              /* 全局空状态 - 数据库完全没数据 */
              <div className="flex flex-col items-center justify-center h-96 text-center">
                <div className="text-6xl mb-4 text-gray-400">📚</div>
                <h3 className="text-2xl font-bold text-gray-800 mb-2">主人，你还没有同步数据喔</h3>
                <p className="text-gray-600 mb-6">同步后可以在这里查看你的收藏内容</p>
                <button 
                  className={`px-6 py-3 bg-primary text-white rounded-full font-medium hover:bg-primary/90 transition-colors ${isSyncing ? 'opacity-70 cursor-not-allowed' : ''}`}
                  onClick={async () => {
                    await handleSync();
                    refreshData();
                  }}
                  disabled={isSyncing}
                >
                  {isSyncing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                      正在同步...
                    </>
                  ) : (
                    '去同步'
                  )}
                </button>
              </div>
            ) : displayItems.length === 0 ? (
              /* 筛选后空状态 - 有数据但没有匹配项 */
              <div className="flex flex-col items-center justify-center h-96 text-center">
                <div className="text-6xl mb-4 text-gray-400">🔍</div>
                <h3 className="text-2xl font-bold text-gray-800 mb-2">此分类下暂无内容</h3>
                <p className="text-gray-600">请尝试其他筛选条件</p>
              </div>
            ) : (
              /* 正常显示数据 */
              <div className="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-8">
                {displayItems.map((item, index) => (
                  <PosterCard
                    key={item.id}
                    id={item.id}
                    name_cn={item.name_cn}
                    cover_url={item.cover_url}
                    score={item.score}
                    tags={item.tags}
                    href={`https://bgm.tv/subject/${item.source_id}`}
                    priority={index < 4}
                    images={item.images}
                  />
                ))}
              </div>
            )}
            
            {/* 加载更多状态和哨兵元素 */}
            {hasMore && (
              <div>
                {/* 加载更多骨架屏 */}
                {isLoadingMore && (
                  <div className="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-8">
                    {[...Array(4)].map((_, index) => (
                      <div key={`loading-more-${index}`} className="aspect-[2/3] rounded-lg bg-gray-200 animate-pulse"></div>
                    ))}
                  </div>
                )}
                
                {/* 哨兵元素 - 用于触发无限滚动 */}
                <div className="flex flex-col items-center justify-center py-10">
                  <div ref={ref} className="h-10 w-10"></div>
                </div>
              </div>
            )}
            
            {/* 到底啦提示 */}
            {!hasMore && items.length > 0 && (
              <div className="flex justify-center py-10 text-gray-500 text-sm">
                ——— 到底啦 ———
              </div>
            )}
          </>
        )}
      </main>

      {/* 右下角悬浮按钮容器 */}
      <div ref={fabRef} className="fixed bottom-8 right-8 flex flex-col items-end gap-3">
        {/* Speed Dial 菜单 */}
        <div className={`flex flex-col items-end gap-3 transition-all duration-300 ${isSpeedDialOpen ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4 pointer-events-none'}`}>
          {/* 菜单项：九宫格导入 */}
          <button
            onClick={() => {
              setIsSpeedDialOpen(false);
              setShowGridModal(true);
            }}
            className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200"
          >
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">九宫格导入</span>
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <UploadCloud className="w-5 h-5 text-primary" />
            </div>
          </button>

          {/* 菜单项：手动添加 */}
          <button
            onClick={() => {
              setIsSpeedDialOpen(false);
              openManualAddDialog();
            }}
            className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200"
          >
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">手动添加</span>
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <PenLine className="w-5 h-5 text-primary" />
            </div>
          </button>

          {/* 菜单项：导入豆瓣数据 */}
          <button
            onClick={() => {
              setIsSpeedDialOpen(false);
              setIsImportDialogOpen(true);
            }}
            className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200"
          >
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">导入豆瓣数据</span>
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <UploadCloud className="w-5 h-5 text-primary" />
            </div>
          </button>
        </div>

        {/* FAB 主按钮 */}
        <button
          onClick={() => setIsSpeedDialOpen(!isSpeedDialOpen)}
          className="w-14 h-14 rounded-full bg-primary text-white shadow-lg hover:-translate-y-1 hover:shadow-xl transition-all duration-300 flex items-center justify-center"
        >
          <div className={`transition-transform duration-300 ${isSpeedDialOpen ? 'rotate-45' : 'rotate-0'}`}>
            {isSpeedDialOpen ? <X className="w-6 h-6" /> : <Plus className="w-6 h-6" />}
          </div>
        </button>
      </div>

      {/* 豆瓣导入对话框 */}
      <DoubanImportDialog
        isOpen={isImportDialogOpen}
        onClose={() => setIsImportDialogOpen(false)}
        onSuccess={refreshData}
      />
      
      {/* 九宫格导入模态框 */}
      <GridImportModal
        isOpen={showGridModal}
        onClose={() => setShowGridModal(false)}
        onSuccess={refreshData}
      />
    </div>
  );
}