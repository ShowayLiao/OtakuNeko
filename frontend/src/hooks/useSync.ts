import { useState, useEffect } from 'react';
import { syncUser, getUserCollectionCount } from '@/lib/api';

interface CollectionCounts {
  anime: number;
  books: number;
  games: number;
  films: number;
}

export const useSync = () => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [collectionCounts, setCollectionCounts] = useState<CollectionCounts>({
    anime: 0,
    books: 0,
    games: 0,
    films: 0
  });

  // 获取各类别的收藏数量
  const fetchCollectionCounts = async () => {
    setIsLoading(true);
    try {
      const [animeCount, booksCount, gamesCount, filmsCount] = await Promise.all([
        getUserCollectionCount('hacci', 2), // 动画
        getUserCollectionCount('hacci', 1), // 书籍
        getUserCollectionCount('hacci', 4), // 游戏
        getUserCollectionCount('hacci', 6)  // 三次元/电影
      ]);
      
      setCollectionCounts({
        anime: animeCount,
        books: booksCount,
        games: gamesCount,
        films: filmsCount
      });
    } catch (error) {
      console.error('Error fetching collection counts:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 组件加载时获取初始数据
  useEffect(() => {
    fetchCollectionCounts();
  }, []);

  const handleSync = async (eventOrOnSuccess?: React.MouseEvent | (() => void)) => {
    setIsSyncing(true);
    // 提示用户同步可能需要几分钟
    alert('Syncing may take a few minutes, please wait.');
    try {
      await syncUser('hacci');
      // 同步成功后重新获取数据
      await fetchCollectionCounts();
      
      // 检查是否传入了onSuccess回调
      const onSuccess = typeof eventOrOnSuccess === 'function' ? eventOrOnSuccess : undefined;
      if (onSuccess) {
        onSuccess();
      }
    } catch (error) {
      alert('Sync failed. Please try again.');
    } finally {
      setIsSyncing(false);
    }
  };

  // 计算总收藏数
  const totalItems = collectionCounts.anime + collectionCounts.books + 
                   collectionCounts.games + collectionCounts.films;

  return {
    isSyncing,
    isLoading,
    collectionCounts,
    totalItems,
    fetchCollectionCounts,
    handleSync
  };
};
