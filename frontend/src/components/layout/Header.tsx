"use client";

import { useState, useEffect } from 'react';
import { Loader2, Settings as SettingsIcon, Search, X } from 'lucide-react';
import { useSync } from '@/hooks/useSync';
import { useSyncStore } from '@/lib/syncStore';
import { useManualAddDialogStore } from '@/lib/manualAddDialogStore';
import { searchMixedSubjects, Subject } from '@/lib/api';
import { useChatContext } from '@/contexts/ChatContext';
import { useSettings } from '@/contexts/SettingsContext';
import { SettingsModal } from '@/components/settings/SettingsModal';
import { GridImportModal } from '@/components/settings/GridImportModal';
import { ManualAddDialog } from '@/components/ManualAddDialog';
import ThemeSwitcher from '@/components/ThemeSwitcher';
import NavPillSkeleton from '@/components/NavPillSkeleton';

interface HeaderProps {
  className?: string;
}

export const Header: React.FC<HeaderProps> = ({ className = '' }) => {
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isGridImportOpen, setIsGridImportOpen] = useState(false);
  const { collectionCounts, isSyncing, isLoading, totalItems, handleSync } = useSync();
  const { fetchCollectionCounts } = useSyncStore();
  const { setReferenceItem } = useChatContext();
  const { openDialog } = useManualAddDialogStore();
  const { settings, userInfo } = useSettings();
  const isLocalUser = !userInfo?.bangumi_id;

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Subject[]>([]);
  const [isSearchDropdownOpen, setIsSearchDropdownOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [showForceSettings, setShowForceSettings] = useState(false);

  useEffect(() => {
    if (!settings.username) {
      setShowForceSettings(true);
    } else {
      setShowForceSettings(false);
    }
  }, [settings.username]);

  // Toggle popover
  const togglePopover = () => {
    setIsPopoverOpen(!isPopoverOpen);
  };

  // Handle search input change
  const handleSearchInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);
  };

  // Handle manual search
  const handleSearch = async () => {
    if (searchQuery.length < 2) {
      setSearchResults([]);
      setIsSearchDropdownOpen(false);
      return;
    }

    setIsSearching(true);
    setIsSearchDropdownOpen(true);
    
    try {
      const results = await searchMixedSubjects(searchQuery);
      setSearchResults(results);
    } catch (error) {
      console.error('Error searching subjects:', error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // Handle Enter key for search
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  // Handle clear search
  const handleClearSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
    setIsSearchDropdownOpen(false);
  };

  // Handle search result selection
  const handleSelectResult = (result: Subject) => {
    console.log(`Selected context: ${result.name_cn || result.name}`);
    
    // Check if we're on the collections page
    const isCollectionsPage = window.location.pathname === '/collections';
    
    if (isCollectionsPage) {
      // On collections page, open the manual add dialog
      openDialog(result);
    } else {
      // On other pages, set as chat reference
      setReferenceItem(result);
    }
    
    setSearchQuery('');
    setSearchResults([]);
    setIsSearchDropdownOpen(false);
    
    // Optional: Focus the chat input
    const chatInput = document.querySelector('textarea');
    if (chatInput && !isCollectionsPage) {
      chatInput.focus();
    }
  };

  // Close search dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.search-container')) {
        setIsSearchDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Close popover when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.popover-container')) {
        setIsPopoverOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <header className={`sticky top-0 z-40 bg-white border-b border-gray-100 flex items-center justify-between p-4 ${className}`}>
      <div className="flex items-center gap-3">
        {/* Search Box */}
        <div className="relative search-container">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                placeholder="搜索收藏..."
                className="w-[32rem] px-4 py-2 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm max-w-full"
                value={searchQuery}
                onChange={handleSearchInputChange}
                onKeyDown={handleKeyDown}
                onFocus={() => setIsSearchDropdownOpen(!!searchQuery && searchResults.length > 0)}
              />
              {searchQuery && (
                <button
                  onClick={handleClearSearch}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <button
              onClick={handleSearch}
              disabled={isSearching || searchQuery.length < 2}
              className="p-2 bg-blue-500 text-white rounded-full hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isSearching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
            </button>
          </div>
          
          {/* Search Dropdown */}
          {isSearchDropdownOpen && searchResults.length > 0 && (
            <div className="absolute left-0 mt-2 w-[32rem] bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden z-50 max-h-96 overflow-y-auto">
              {searchResults.map((result, index) => (
                <div
                  key={result.id ?? `search-result-${index}`}
                  className="p-3 hover:bg-gray-50 cursor-pointer flex items-center justify-between transition-colors"
                  onClick={() => handleSelectResult(result)}
                >
                  <div className="flex-1">
                    <div className="font-medium text-sm">{result.name_cn || result.name}</div>
                    <div className="text-xs text-gray-500">{result.name}</div>
                  </div>
                  <div className="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded">{(result.score ?? result.rating_details?.score ?? 0).toFixed(1)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {/* Theme Switcher */}
        <ThemeSwitcher />
        
        {/* Data Status Capsule */}
        {isLoading ? (
          <NavPillSkeleton width="w-28" />
        ) : (
          <div className="relative popover-container">
            <button
              className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 shadow-sm rounded-full px-4 py-2 text-sm font-medium flex items-center justify-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
              onClick={togglePopover}
            >
              <svg className="w-4 h-4 fill-primary" viewBox="0 0 1025 1024" xmlns="http://www.w3.org/2000/svg"><path d="M512.118374 131.072L603.766374 317.44c20.48 41.472 59.392 70.144 104.96 76.8l205.824 30.208-148.992 145.92c-32.768 32.256-47.616 78.336-39.936 123.392l35.328 205.824-183.296-96.768c-19.968-10.752-42.496-16.384-65.024-16.384-22.528 0-45.056 5.632-65.024 16.384l-183.296 96.768 35.328-205.824c7.68-45.056-7.168-91.136-39.936-123.392L109.686374 424.448 314.998374 394.24c45.568-6.656 84.992-35.328 104.96-76.8l92.16-186.368m0-112.64c-20.48 0-41.472 10.752-51.712 32.256L346.742374 281.6c-8.192 16.896-24.576 29.184-43.52 31.744L49.270374 350.208C2.166374 357.376-16.777626 415.232 17.526374 449.024l183.808 180.224c13.312 13.312 19.968 32.256 16.384 51.2l-43.52 253.952c-6.144 37.376 23.552 67.584 56.832 67.584 8.704 0 17.92-2.048 27.136-6.656L484.982374 875.52c8.192-4.608 17.92-6.656 27.136-6.656 9.216 0 18.432 2.048 27.136 6.656l226.816 119.808c8.704 4.608 17.92 6.656 27.136 6.656 33.792 0 63.488-30.208 56.832-67.584l-43.52-253.952c-3.072-18.944 3.072-37.888 16.384-51.2l183.808-180.224c34.304-33.28 15.36-91.648-32.256-98.304l-253.952-36.864c-18.944-2.56-35.328-14.848-43.52-31.744L563.830374 50.688c-10.752-21.504-31.232-32.256-51.712-32.256z"></path></svg>
              {totalItems} 收藏
            </button>

            {isPopoverOpen && (
              <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden z-50">
                <div className="p-3">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">收藏统计</h3>
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-600">动画:</span>
                      <span className="text-gray-900">{collectionCounts.anime}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-600">书籍:</span>
                      <span className="text-gray-900">{collectionCounts.books}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-600">游戏:</span>
                      <span className="text-gray-900">{collectionCounts.games}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-600">剧集:</span>
                      <span className="text-gray-900">{collectionCounts.films}</span>
                    </div>
                  </div>
                </div>

                <div className="p-3 border-t border-gray-100 space-y-2">
                  {isLocalUser ? (
                    <>
                      <button
                        className="w-full py-2 px-3 bg-primary text-white font-medium rounded-lg shadow-sm text-sm hover:bg-primary/90 transition-colors"
                        onClick={() => {
                          setIsGridImportOpen(true);
                          setIsPopoverOpen(false);
                        }}
                      >
                        填写宫格图
                      </button>
                      <button
                        className="w-full py-2 px-3 bg-white border border-gray-200 text-gray-700 font-medium rounded-lg shadow-sm text-sm hover:bg-gray-50 transition-colors"
                        onClick={() => {
                          openDialog();
                          setIsPopoverOpen(false);
                        }}
                      >
                        手动增加
                      </button>
                    </>
                  ) : (
                    <button
                      className={`w-full py-2 px-3 bg-primary text-white font-medium rounded-lg shadow-sm text-sm hover:bg-primary/90 transition-colors ${isSyncing ? 'opacity-70 cursor-not-allowed' : ''}`}
                      onClick={async () => {
                        await handleSync();
                        setIsPopoverOpen(false);
                      }}
                      disabled={isSyncing}
                    >
                      {isSyncing ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                          正在同步...
                        </>
                      ) : (
                        '一键同步'
                      )}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* User Avatar / Settings Trigger */}
        <button
          onClick={() => setIsSettingsOpen(true)}
          className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-full flex items-center justify-center font-bold hover:bg-purple-200 dark:hover:bg-purple-900/50 transition-colors cursor-pointer overflow-hidden"
          title="设置"
        >
          {userInfo?.avatar?.large ? (
            <img 
              src={userInfo.avatar.large} 
              alt={userInfo.nickname}
              className="w-full h-full rounded-full object-cover"
            />
          ) : settings.username ? settings.username.charAt(0).toUpperCase() : 'H'}
        </button>
      </div>
      
      {/* Settings Modal */}
      <SettingsModal 
        isOpen={isSettingsOpen || showForceSettings} 
        onClose={() => setIsSettingsOpen(false)}
        forceOpen={showForceSettings}
      />
      
      {/* Grid Import Modal */}
      <GridImportModal 
        isOpen={isGridImportOpen} 
        onClose={() => setIsGridImportOpen(false)} 
      />
      
      {/* Manual Add Dialog */}
      <ManualAddDialog
        onSuccess={() => {
          if (window.location.pathname === '/collections') {
            window.dispatchEvent(new CustomEvent('refreshCollections'));
          }
        }}
      />
    </header>
  );
};
