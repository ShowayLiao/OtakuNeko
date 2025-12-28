"use client";

import { useState } from 'react';
import { Loader2, LayoutGrid, Plus } from 'lucide-react';
import { useSync } from '@/hooks/useSync';
import { useSettings } from '@/contexts/SettingsContext';
import { useManualAddDialogStore } from '@/lib/manualAddDialogStore';
import { GridImportModal } from '@/components/settings/GridImportModal';

export const EmptyState: React.FC = () => {
  const { isSyncing, handleSync } = useSync();
  const { settings, userInfo } = useSettings();
  const { openDialog } = useManualAddDialogStore();
  const [showGridModal, setShowGridModal] = useState(false);

  const isLocalUser = !userInfo?.bangumi_id;

  const handleSyncClick = async () => {
    await handleSync();
  };

  const handleGridImportClick = () => {
    setShowGridModal(true);
  };

  const handleManualAddClick = () => {
    openDialog();
  };

  return (
    <>
      <div className="flex flex-col items-center justify-center h-full p-6">
        <div className="mb-8">
          {isLocalUser ? (
            <LayoutGrid className="w-32 h-32 text-primary" />
          ) : (
            <svg className="w-32 h-32 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          )}
        </div>

        {isLocalUser ? (
          <>
            <h1 className="text-3xl font-bold text-gray-800 mb-3">开始构建你的收藏库</h1>
            <p className="text-lg text-gray-600 mb-8 text-center max-w-md">手动填写动画喜好格子图，快速生成你的个人二次元画像，让 AI 更懂你。</p>

            <div className="flex gap-4">
              <button
                className="py-4 px-8 bg-primary text-white font-bold rounded-lg shadow-lg text-xl hover:bg-primary/90 transition-colors transform hover:scale-105"
                onClick={handleGridImportClick}
              >
                <LayoutGrid className="w-5 h-5 inline mr-2" />
                填写格子图
              </button>
              <button
                className="py-4 px-8 bg-white border border-gray-200 text-gray-700 font-bold rounded-lg shadow-lg text-xl hover:bg-gray-50 transition-colors transform hover:scale-105"
                onClick={handleManualAddClick}
              >
                <Plus className="w-5 h-5 inline mr-2" />
                手动录入
              </button>
            </div>
          </>
        ) : (
          <>
            <h1 className="text-3xl font-bold text-gray-800 mb-3">Connect your Bangumi</h1>
            <p className="text-lg text-gray-600 mb-8 text-center max-w-md">同步你的收藏数据，让 AI 更懂你的口味。</p>

            <button
              className={`py-4 px-8 bg-primary text-white font-bold rounded-lg shadow-lg text-xl hover:bg-primary/90 transition-colors transform hover:scale-105 ${isSyncing ? 'opacity-70 cursor-not-allowed' : ''}`}
              onClick={handleSyncClick}
              disabled={isSyncing}
            >
              {isSyncing ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin inline mr-2" />
                  正在同步...
                </>
              ) : (
                '一键同步'
              )}
            </button>
          </>
        )}
      </div>

      <GridImportModal
        isOpen={showGridModal}
        onClose={() => setShowGridModal(false)}
      />
    </>
  );
};
