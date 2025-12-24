"use client";

import { useState, useEffect } from 'react';
import { useSync } from '@/hooks/useSync';
import { getUserCollections, CollectionWithSubject } from '@/lib/api';
import { useChatContext } from '@/contexts/ChatContext';
import ThemeSwitcher from '@/components/ThemeSwitcher';

interface HeaderProps {
  className?: string;
}

export const Header: React.FC<HeaderProps> = ({ className = '' }) => {
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const { collectionCounts, isSyncing, totalItems, handleSync, fetchCollectionCounts } = useSync();
  const { setReferenceItem } = useChatContext();

  // Search related states
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<CollectionWithSubject[]>([]);
  const [isSearchDropdownOpen, setIsSearchDropdownOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);

  // Toggle popover
  const togglePopover = () => {
    setIsPopoverOpen(!isPopoverOpen);
  };

  // Handle search input change
  const handleSearchInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);

    if (query.length > 0) {
      setIsSearching(true);
      setIsSearchDropdownOpen(true);
      
      try {
        const results = await getUserCollections(query, 2); // 2 for anime type
        setSearchResults(results);
      } catch (error) {
        console.error('Error searching collections:', error);
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    } else {
      setSearchResults([]);
      setIsSearchDropdownOpen(false);
    }
  };

  // Handle search result selection
  const handleSelectResult = (result: CollectionWithSubject) => {
    console.log(`Selected context: ${result.subject.name_cn || result.subject.name}`);
    setReferenceItem(result.subject);
    setSearchQuery('');
    setSearchResults([]);
    setIsSearchDropdownOpen(false);
    
    // Optional: Focus the chat input
    const chatInput = document.querySelector('textarea');
    if (chatInput) {
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
    <header className={`bg-white border-b border-gray-100 flex items-center justify-between p-4 ${className}`}>
      <div className="flex items-center gap-3">
        {/* Search Box */}
        <div className="relative search-container">
          <input
            type="text"
            placeholder="搜索收藏..."
            className="w-[32rem] px-4 py-2 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm max-w-full"
            value={searchQuery}
            onChange={handleSearchInputChange}
            onFocus={() => setIsSearchDropdownOpen(!!searchQuery)}
          />
          
          {/* Search Dropdown */}
          {isSearchDropdownOpen && searchResults.length > 0 && (
            <div className="absolute left-0 mt-2 w-[32rem] bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden z-50 max-h-96 overflow-y-auto">
              {searchResults.map((result) => (
                <div
                  key={result.subject.id}
                  className="p-3 hover:bg-gray-50 cursor-pointer flex items-center justify-between transition-colors"
                  onClick={() => handleSelectResult(result)}
                >
                  <div className="flex-1">
                    <div className="font-medium text-sm">{result.subject.name_cn || result.subject.name}</div>
                    <div className="text-xs text-gray-500">{result.subject.name}</div>
                  </div>
                  <div className="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded">{(result.subject.score ?? result.subject.rating_details?.score ?? result.subject.rating?.score ?? 0).toFixed(1)}</div>
                </div>
              ))}
            </div>
          )}
          
          {/* Searching Indicator */}
          {isSearching && (
            <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
              <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin"></div>
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {/* Theme Switcher */}
        <ThemeSwitcher />
        
        {/* Data Status Capsule */}
        {totalItems > 0 && (
          <div className="relative popover-container">
            <button
              className="bg-gray-100 text-gray-700 rounded-full px-4 py-1.5 text-sm flex items-center gap-2 hover:bg-gray-200 transition-colors"
              onClick={togglePopover}
            >
              <svg className="w-4 h-4 fill-primary" viewBox="0 0 1025 1024" xmlns="http://www.w3.org/2000/svg"><path d="M512.118374 131.072L603.766374 317.44c20.48 41.472 59.392 70.144 104.96 76.8l205.824 30.208-148.992 145.92c-32.768 32.256-47.616 78.336-39.936 123.392l35.328 205.824-183.296-96.768c-19.968-10.752-42.496-16.384-65.024-16.384-22.528 0-45.056 5.632-65.024 16.384l-183.296 96.768 35.328-205.824c7.68-45.056-7.168-91.136-39.936-123.392L109.686374 424.448 314.998374 394.24c45.568-6.656 84.992-35.328 104.96-76.8l92.16-186.368m0-112.64c-20.48 0-41.472 10.752-51.712 32.256L346.742374 281.6c-8.192 16.896-24.576 29.184-43.52 31.744L49.270374 350.208C2.166374 357.376-16.777626 415.232 17.526374 449.024l183.808 180.224c13.312 13.312 19.968 32.256 16.384 51.2l-43.52 253.952c-6.144 37.376 23.552 67.584 56.832 67.584 8.704 0 17.92-2.048 27.136-6.656L484.982374 875.52c8.192-4.608 17.92-6.656 27.136-6.656 9.216 0 18.432 2.048 27.136 6.656l226.816 119.808c8.704 4.608 17.92 6.656 27.136 6.656 33.792 0 63.488-30.208 56.832-67.584l-43.52-253.952c-3.072-18.944 3.072-37.888 16.384-51.2l183.808-180.224c34.304-33.28 15.36-91.648-32.256-98.304l-253.952-36.864c-18.944-2.56-35.328-14.848-43.52-31.744L563.830374 50.688c-10.752-21.504-31.232-32.256-51.712-32.256z"></path></svg>
              {totalItems} 收藏
            </button>

            {/* Popover */}
            {isPopoverOpen && (
              <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden z-50">
                {/* Collection Stats */}
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

                {/* Sync Button */}
                <div className="p-3 border-t border-gray-100">
                  <button
                    className={`w-full py-2 px-3 bg-primary text-white font-medium rounded-lg shadow-sm text-sm hover:bg-primary/90 transition-colors ${isSyncing ? 'opacity-70 cursor-not-allowed' : ''}`}
                    onClick={async () => {
                      await handleSync();
                      setIsPopoverOpen(false);
                    }}
                    disabled={isSyncing}
                  >
                    {isSyncing ? '正在同步...' : '一键同步'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* User Avatar */}
        <div className="w-10 h-10 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center font-bold">
          H
        </div>
      </div>
    </header>
  );
};
