import { create } from 'zustand';
import { syncUser, getUserCollections } from '@/lib/api';

interface CollectionCounts {
  anime: number;
  books: number;
  games: number;
  films: number;
}

interface SyncState {
  isSyncing: boolean;
  isLoading: boolean;
  collectionCounts: CollectionCounts;
  lastSyncTime: Date | null;
  syncError: string | null;
  setSyncing: (syncing: boolean) => void;
  setLoading: (loading: boolean) => void;
  setCollectionCounts: (counts: CollectionCounts) => void;
  setLastSyncTime: (time: Date | null) => void;
  setSyncError: (error: string | null) => void;
  fetchCollectionCounts: () => Promise<void>;
  performSync: (source: string, subjectType?: number) => Promise<void>;
}

export const useSyncStore = create<SyncState>((set, get) => ({
  isSyncing: false,
  isLoading: true,
  collectionCounts: {
    anime: 0,
    books: 0,
    games: 0,
    films: 0
  },
  lastSyncTime: null,
  syncError: null,

  setSyncing: (syncing) => set({ isSyncing: syncing }),
  setLoading: (loading) => set({ isLoading: loading }),
  setCollectionCounts: (counts) => set({ collectionCounts: counts }),
  setLastSyncTime: (time) => set({ lastSyncTime: time }),
  setSyncError: (error) => set({ syncError: error }),

  fetchCollectionCounts: async () => {
    set({ isLoading: true });
    try {
      // 使用新的getUserCollections方法获取各类型的收藏数量
      const [animeResult, booksResult, gamesResult, filmsResult] = await Promise.all([
        getUserCollections(2, undefined, undefined, 1, 0), // 动画
        getUserCollections(1, undefined, undefined, 1, 0), // 书籍
        getUserCollections(4, undefined, undefined, 1, 0), // 游戏
        getUserCollections(6, undefined, undefined, 1, 0)  // 三次元
      ]);

      set({
        collectionCounts: {
          anime: animeResult.total,
          books: booksResult.total,
          games: gamesResult.total,
          films: filmsResult.total
        }
      });
    } catch (error) {
      console.error('Error fetching collection counts:', error);
    } finally {
      set({ isLoading: false });
    }
  },

  performSync: async (source: string, subjectType?: number) => {
    const { isSyncing } = get();
    if (isSyncing) {
      console.warn('Sync is already in progress, ignoring duplicate request');
      return;
    }

    set({ isSyncing: true, syncError: null });

    try {
      await syncUser(source, subjectType);
      await get().fetchCollectionCounts();
      set({ lastSyncTime: new Date() });
    } catch (error) {
      console.error('Sync failed:', error);
      const errorMessage = error instanceof Error ? error.message : '同步失败，请稍后重试';
      set({ syncError: errorMessage });
      throw error;
    } finally {
      set({ isSyncing: false });
    }
  }
}));

export const getTotalItems = (counts: CollectionCounts) => {
  return counts.anime + counts.books + counts.games + counts.films;
};
