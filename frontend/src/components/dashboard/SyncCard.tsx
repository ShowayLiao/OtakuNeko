"use client";

import { useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { useSync } from '@/hooks/useSync';
import { useSettings } from '@/contexts/SettingsContext';
import { useManualAddDialogStore } from '@/lib/manualAddDialogStore';
import { GridImportModal } from '@/components/settings/GridImportModal';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/Card';

interface SyncCardProps {
  onSyncSuccess: () => void;
  className?: string;
}

export const SyncCard: React.FC<SyncCardProps> = ({ 
  onSyncSuccess, 
  className = '' 
}) => {
  const { userInfo } = useSettings();
  const { isSyncing, collectionCounts, handleSync } = useSync();
  const { openDialog } = useManualAddDialogStore();
  const [showGridModal, setShowGridModal] = useState(false);

  const hasBangumiAccount = !!userInfo?.bangumi_id;

  console.log('SyncCard UserInfo:', userInfo, 'BangumiID:', userInfo?.bangumi_id, 'HasBangumiAccount:', hasBangumiAccount);

  const handleSyncClick = async () => {
    await handleSync();
    onSyncSuccess();
  };

  const handleGridImportClick = () => {
    setShowGridModal(true);
  };

  const handleManualAddClick = () => {
    openDialog();
  };

  return (
    <>
      <Card className={`w-[180px] flex flex-col ${className}`}>
        <CardHeader className="pb-4">
          <div className="text-xs text-gray-500">
            收藏
          </div>
        </CardHeader>
        
        <CardContent className="flex-1">
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
        </CardContent>
        
        <CardFooter className="pt-4">
          {hasBangumiAccount ? (
            <Button 
              className="w-full flex items-center justify-center gap-2 bg-[#FFB347] text-[#8B4513] hover:bg-[#FF8C00] hover:text-white"
              onClick={handleSyncClick}
              disabled={isSyncing}
            >
              {isSyncing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  正在同步...
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4" />
                  一键同步
                </>
              )}
            </Button>
          ) : (
            <div className="space-y-2 w-full">
              <Button 
                className="w-full bg-[#FFB347] text-[#8B4513] hover:bg-[#FF8C00] hover:text-white"
                onClick={handleGridImportClick}
              >
                填写宫格图
              </Button>
              <Button 
                variant="outline"
                className="w-full"
                onClick={handleManualAddClick}
              >
                手动增加
              </Button>
            </div>
          )}
        </CardFooter>
      </Card>

      <GridImportModal
        isOpen={showGridModal}
        onClose={() => setShowGridModal(false)}
      />
    </>
  );
};
