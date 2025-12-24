"use client";

import { useSync } from '@/hooks/useSync';

export const EmptyState: React.FC = () => {
  const { isSyncing, handleSync } = useSync();

  return (
    <div className="flex flex-col items-center justify-center h-full p-6">
      {/* 二次元风格图标 - 使用一个简单的SVG图标作为示例 */}
      <div className="mb-8">
        <svg className="w-32 h-32 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      </div>

      <h1 className="text-3xl font-bold text-gray-800 mb-3">Connect your Bangumi</h1>
      <p className="text-lg text-gray-600 mb-8 text-center max-w-md">同步你的收藏数据，让 AI 更懂你的口味。</p>

      <button
        className={`py-4 px-8 bg-[#FFB347] text-[#8B4513] font-bold rounded-lg shadow-lg text-xl hover:bg-[#FF8C00] hover:text-white transition-colors transform hover:scale-105 ${isSyncing ? 'opacity-70 cursor-not-allowed' : ''}`}
        onClick={handleSync}
        disabled={isSyncing}
      >
        {isSyncing ? '正在同步...' : '一键同步'}
      </button>
    </div>
  );
};
