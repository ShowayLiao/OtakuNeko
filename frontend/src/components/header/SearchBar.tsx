'use client';

import React, { useState } from 'react';
import { SearchBar as LobeSearchBar, SearchBarProps } from '@lobehub/ui';

interface HeaderSearchBarProps extends Omit<SearchBarProps, 'onSearch'> {
  onSearch?: (value: string) => void;
  className?: string;
}

const SearchBar: React.FC<HeaderSearchBarProps> = ({
  onSearch,
  className,
  ...props
}) => {
  const [value, setValue] = useState<string>('');

  const handleSearch = (searchValue: string) => {
    setValue(searchValue);
    onSearch?.(searchValue);
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
        onSearch={handleSearch}
      />
    </div>
  );
};

export default SearchBar;
