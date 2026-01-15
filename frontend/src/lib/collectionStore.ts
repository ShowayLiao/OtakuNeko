import { create } from 'zustand';
import { persist } from 'zustand/middleware';

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

interface CollectionState {
  items: CollectionItem[];
  loadingState: LoadingState;
  error: string | null;
  searchQuery: string;
  activeFilter: string;
  setItems: (items: CollectionItem[]) => void;
  setLoadingState: (state: LoadingState) => void;
  setError: (error: string | null) => void;
  setSearchQuery: (query: string) => void;
  setActiveFilter: (filter: string) => void;
  resetState: () => void;
  getFilteredItems: () => CollectionItem[];
}

const initialState = {
  items: [],
  loadingState: 'idle' as LoadingState,
  error: null,
  searchQuery: '',
  activeFilter: '全部'
};

export const useCollectionStore = create<CollectionState>()(
  persist(
    (set, get) => ({
      ...initialState,
      setItems: (items) => set({ items }),
      setLoadingState: (loadingState) => set({ loadingState }),
      setError: (error) => set({ error }),
      setSearchQuery: (searchQuery) => set({ searchQuery }),
      setActiveFilter: (activeFilter) => set({ activeFilter }),
      resetState: () => set(initialState),
      getFilteredItems: () => {
        const { items, searchQuery, activeFilter } = get();
        return items.filter(item => {
          const matchesSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase());
          const matchesFilter = activeFilter === '全部' ||
            item.status === activeFilter ||
            (activeFilter === '动画' && item.type === 'anime') ||
            (activeFilter === '游戏' && item.type === 'game') ||
            (activeFilter === '书籍' && item.type === 'book');
          return matchesSearch && matchesFilter;
        });
      }
    }),
    {
      name: 'collection-storage',
      partialize: (state) => ({
        searchQuery: state.searchQuery,
        activeFilter: state.activeFilter
      })
    }
  )
);
