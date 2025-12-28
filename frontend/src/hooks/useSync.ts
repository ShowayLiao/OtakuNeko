import { useSyncStore, getTotalItems } from '@/lib/syncStore';
import { useEffect } from 'react';
import { useToast } from '@/components/ui/Toast';
import { useSettings } from '@/contexts/SettingsContext';

export const useSync = () => {
  const { settings } = useSettings();
  const {
    isSyncing,
    isLoading,
    collectionCounts,
    lastSyncTime,
    syncError,
    fetchCollectionCounts,
    performSync
  } = useSyncStore();

  const { toast } = useToast();

  useEffect(() => {
    if (settings.username) {
      fetchCollectionCounts(settings.username);
    }
  }, [fetchCollectionCounts, settings.username]);

  const handleSync = async () => {
    if (!settings.username) {
      toast({
        type: 'error',
        message: '请先设置用户名'
      });
      return;
    }

    try {
      await performSync(settings.username);
      toast({
        type: 'success',
        message: '同步已完成！'
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '同步失败，请稍后重试';
      toast({
        type: 'error',
        message: errorMessage
      });
    }
  };

  return {
    isSyncing,
    isLoading,
    collectionCounts,
    totalItems: getTotalItems(collectionCounts),
    lastSyncTime,
    syncError,
    handleSync
  };
};
