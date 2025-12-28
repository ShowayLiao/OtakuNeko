import { create } from 'zustand';
import { syncUser, getUserCollectionCount } from '@/lib/api';

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
  fetchCollectionCounts: (username: string) => Promise<void>;
  performSync: (username: string) => Promise<void>;
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

  fetchCollectionCounts: async (username: string) => {
    if (!username) {
      console.warn('Username is required for fetching collection counts');
      return;
    }

    set({ isLoading: true });
    try {
      const [animeCount, booksCount, gamesCount, filmsCount] = await Promise.all([
        getUserCollectionCount(username, 2),
        getUserCollectionCount(username, 1),
        getUserCollectionCount(username, 4),
        getUserCollectionCount(username, 6)
      ]);

      set({
        collectionCounts: {
          anime: animeCount,
          books: booksCount,
          games: gamesCount,
          films: filmsCount
        }
      });
    } catch (error) {
      console.error('Error fetching collection counts:', error);
    } finally {
      set({ isLoading: false });
    }
  },

  performSync: async (username: string) => {
    if (!username) {
      console.warn('Username is required for sync');
      set({ syncError: '用户名不能为空' });
      return;
    }

    const { isSyncing } = get();
    if (isSyncing) {
      console.warn('Sync is already in progress, ignoring duplicate request');
      return;
    }

    set({ isSyncing: true, syncError: null });

    try {
      await syncUser(username);
      await get().fetchCollectionCounts(username);
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
