"use client";

import { useState, useEffect } from 'react';
import { syncUser, getUserCollectionCount } from '@/lib/api';

interface SyncCardProps {
  onSyncSuccess: () => void;
  className?: string;
}

export const SyncCard: React.FC<SyncCardProps> = ({ 
  onSyncSuccess, 
  className = '' 
}) => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [collectionCounts, setCollectionCounts] = useState({
    anime: 0,
    books: 0,
    games: 0,
    films: 0
  });

  // 获取各类别的收藏数量
  const fetchCollectionCounts = async () => {
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
    }
  };

  // 组件加载时获取初始数据
  useEffect(() => {
    fetchCollectionCounts();
  }, []);

  const handleSync = async () => {
    setIsSyncing(true);
    // 提示用户同步可能需要几分钟
    alert('Syncing may take a few minutes, please wait.');
    try {
      await syncUser('hacci');
      // 同步成功后重新获取数据
      await fetchCollectionCounts();
      onSyncSuccess();
    } catch (error) {
      alert('Sync failed. Please try again.');
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className={`bg-white rounded-2xl shadow-xl w-[180px] flex flex-col ${className}`}>
      {/* Statistics Section */}
      <div className="p-4 flex-1">
        <div className="text-xs text-gray-500 mb-2">收藏</div>
        <div className="space-y-2">
          <div className="flex justify-between">
            <span className="text-sm text-gray-600">动画:</span>
            <span className="text-sm font-medium text-gray-900">{collectionCounts.anime}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-sm text-gray-600">书籍:</span>
            <span className="text-sm font-medium text-gray-900">{collectionCounts.books}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-sm text-gray-600">游戏:</span>
            <span className="text-sm font-medium text-gray-900">{collectionCounts.games}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-sm text-gray-600">剧集:</span>
            <span className="text-sm font-medium text-gray-900">{collectionCounts.films}</span>
          </div>
        </div>
      </div>
      
      {/* Sync Button Section */}
      <div className="p-4 border-t border-gray-100">
        <button 
          className={`w-full py-3 px-4 bg-[#FFB347] text-[#8B4513] font-medium rounded-xl shadow-md hover:bg-[#FF8C00] hover:text-white hover:shadow-lg transition-all duration-200 ${isSyncing ? 'opacity-70 cursor-not-allowed' : ''}`}
          onClick={handleSync}
          disabled={isSyncing}
        >
          {isSyncing ? '正在同步... ' : '一键同步'}
        </button>
      </div>
    </div>
  );
};
