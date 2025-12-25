"use client";

import React, { useState, useRef, useEffect } from 'react';

interface SortOption {
  label: string;
  value: string;
}

interface SortDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: SortOption[];
}

export function SortDropdown({ value, onChange, options }: SortDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 获取当前选中的选项
  const selectedOption = options.find(option => option.value === value);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 主按钮 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2 rounded-full font-medium transition-all duration-200 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 shadow-sm hover:shadow hover:bg-gray-50 dark:hover:bg-gray-750 cursor-pointer flex items-center gap-2"
      >
        {selectedOption?.label || options[0].label}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* 下拉菜单 */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 rounded-lg bg-white dark:bg-gray-800 shadow-lg z-50">
          {options.map(option => (
            <button
              key={option.value}
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={`w-full text-left px-4 py-3 transition-colors duration-200 ${option.value === value
                ? 'text-primary font-medium flex items-center gap-2'
                : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}
              `}
            >
              {option.value === value && (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="w-4 h-4"
                >
                  <path
                    fillRule="evenodd"
                    d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}