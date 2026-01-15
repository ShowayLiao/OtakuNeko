"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { Subject } from '@/lib/api';

interface HeaderContextType {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  searchResults: Subject[];
  setSearchResults: (results: Subject[]) => void;
  isSearchDropdownOpen: boolean;
  setIsSearchDropdownOpen: (open: boolean) => void;
  isSearching: boolean;
  setIsSearching: (searching: boolean) => void;
  isPopoverOpen: boolean;
  setIsPopoverOpen: (open: boolean) => void;
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  isGridImportOpen: boolean;
  setIsGridImportOpen: (open: boolean) => void;
  isSubjectSearchOpen: boolean;
  setIsSubjectSearchOpen: (open: boolean) => void;
  isDoubanImportOpen: boolean;
  setIsDoubanImportOpen: (open: boolean) => void;
  isCollectionEditOpen: boolean;
  setIsCollectionEditOpen: (open: boolean) => void;
  isCollectionManagerOpen: boolean;
  setIsCollectionManagerOpen: (open: boolean) => void;
  clearSearch: () => void;
}

const HeaderContext = createContext<HeaderContextType | undefined>(undefined);

export function HeaderProvider({ children }: { children: ReactNode }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Subject[]>([]);
  const [isSearchDropdownOpen, setIsSearchDropdownOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isGridImportOpen, setIsGridImportOpen] = useState(false);
  const [isSubjectSearchOpen, setIsSubjectSearchOpen] = useState(false);
  const [isDoubanImportOpen, setIsDoubanImportOpen] = useState(false);
  const [isCollectionEditOpen, setIsCollectionEditOpen] = useState(false);
  const [isCollectionManagerOpen, setIsCollectionManagerOpen] = useState(false);

  const clearSearch = useCallback(() => {
    setSearchQuery('');
    setSearchResults([]);
    setIsSearchDropdownOpen(false);
  }, []);

  return (
    <HeaderContext.Provider
      value={{
        searchQuery,
        setSearchQuery,
        searchResults,
        setSearchResults,
        isSearchDropdownOpen,
        setIsSearchDropdownOpen,
        isSearching,
        setIsSearching,
        isPopoverOpen,
        setIsPopoverOpen,
        isSettingsOpen,
        setIsSettingsOpen,
        isGridImportOpen,
        setIsGridImportOpen,
        isSubjectSearchOpen,
        setIsSubjectSearchOpen,
        isDoubanImportOpen,
        setIsDoubanImportOpen,
        isCollectionEditOpen,
        setIsCollectionEditOpen,
        isCollectionManagerOpen,
        setIsCollectionManagerOpen,
        clearSearch,
      }}
    >
      {children}
    </HeaderContext.Provider>
  );
}

export function useHeaderContext() {
  const context = useContext(HeaderContext);
  if (context === undefined) {
    throw new Error('useHeaderContext must be used within a HeaderProvider');
  }
  return context;
}
