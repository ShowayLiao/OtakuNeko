'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { SearchBar as LobeSearchBar, SearchBarProps } from '@lobehub/ui';
import { debounce } from 'lodash';

interface HeaderSearchBarProps extends Omit<SearchBarProps, 'onSearch'> {
  onSearch?: (value: string) => void;
  className?: string;
  debounceDelay?: number;
}

const SearchBar: React.FC<HeaderSearchBarProps> = ({
  onSearch,
  className,
  debounceDelay = 500,
  ...props
}) => {
  const [value, setValue] = useState<string>('');

  // 防抖处理函数
  const debouncedSearch = useCallback(
    debounce((searchValue: string) => {
      onSearch?.(searchValue);
    }, debounceDelay),
    [onSearch, debounceDelay]
  );

  // 组件卸载时清除防抖定时器
  useEffect(() => {
    return () => {
      debouncedSearch.cancel();
    };
  }, [debouncedSearch]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const searchValue = e.target.value;
    setValue(searchValue);
    debouncedSearch(searchValue);
  };

  return (
    <div className={className}>
      <LobeSearchBar
        {...props}
        placeholder="搜索..."
        variant="filled"
        enableShortKey={true}
        shortKey="f"
        value={value}
        onChange={handleChange}
      />
    </div>
  );
};

// 导出防抖工具函数
export const createDebouncedSearch = (delay: number = 500) => {
  return debounce((callback: (value: string) => void, value: string) => {
    callback(value);
  }, delay);
};

export default SearchBar;
