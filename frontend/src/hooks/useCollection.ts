import { useEffect } from 'react';
import { useCollectionStore } from '@/lib/collectionStore';

export interface UseCollectionOptions {
  fetchItems?: () => Promise<import('@/lib/collectionStore').CollectionItem[]>;
  autoFetch?: boolean;
}

export const useCollection = (options?: UseCollectionOptions) => {
  const {
    items,
    loadingState,
    error,
    searchQuery,
    activeFilter,
    setItems,
    setLoadingState,
    setError,
    setSearchQuery,
    setActiveFilter,
    resetState,
    getFilteredItems
  } = useCollectionStore();

  const filteredItems = getFilteredItems();

  useEffect(() => {
    if (options?.autoFetch && options?.fetchItems) {
      const loadItems = async () => {
        setLoadingState('loading');
        try {
          const fetchFn = options.fetchItems;
          if (fetchFn) {
            const data = await fetchFn();
            setItems(data);
            setLoadingState('success');
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : '加载失败');
          setLoadingState('error');
        }
      };
      loadItems();
    }
  }, [options?.autoFetch, options?.fetchItems, setItems, setLoadingState, setError]);

  const handleSearch = (query: string) => {
    setSearchQuery(query);
  };

  const handleFilter = (filter: string) => {
    setActiveFilter(filter);
  };

  const handleRetry = async () => {
    if (options?.fetchItems) {
      setLoadingState('loading');
      try {
        const fetchFn = options.fetchItems;
        if (fetchFn) {
          const data = await fetchFn();
          setItems(data);
          setLoadingState('success');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败');
        setLoadingState('error');
      }
    }
  };

  return {
    items,
    filteredItems,
    loadingState,
    error,
    searchQuery,
    activeFilter,
    handleSearch,
    handleFilter,
    handleRetry,
    resetState
  };
};
