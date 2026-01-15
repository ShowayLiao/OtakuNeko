"use client";

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';

interface SortOption {
  label: string;
  value: string;
  icon?: React.ReactNode;
}

interface SortDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: SortOption[];
  className?: string;
  ariaLabel?: string;
}

export function SortDropdown({ value, onChange, options, className, ariaLabel = "排序选项" }: SortDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuItemsRef = useRef<(HTMLButtonElement | null)[]>([]);

  const handleClickOutside = useCallback((event: MouseEvent) => {
    if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
      setIsOpen(false);
      setFocusedIndex(-1);
    }
  }, []);

  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [handleClickOutside]);

  useEffect(() => {
    if (isOpen && focusedIndex >= 0) {
      menuItemsRef.current[focusedIndex]?.focus();
    }
  }, [isOpen, focusedIndex]);

  const selectedOption = options.find(option => option.value === value);

  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          setFocusedIndex(0);
        } else {
          setFocusedIndex(prev => (prev + 1) % options.length);
        }
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (isOpen) {
          setFocusedIndex(prev => (prev - 1 + options.length) % options.length);
        }
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (isOpen && focusedIndex >= 0) {
          onChange(options[focusedIndex].value);
          setIsOpen(false);
          setFocusedIndex(-1);
        } else {
          setIsOpen(!isOpen);
        }
        break;
      case 'Escape':
        event.preventDefault();
        setIsOpen(false);
        setFocusedIndex(-1);
        buttonRef.current?.focus();
        break;
      case 'Tab':
        setIsOpen(false);
        setFocusedIndex(-1);
        break;
    }
  }, [isOpen, focusedIndex, options, onChange]);

  const handleOptionClick = useCallback((optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
    setFocusedIndex(-1);
    buttonRef.current?.focus();
  }, [onChange]);

  const handleToggle = useCallback(() => {
    setIsOpen(prev => !prev);
    setFocusedIndex(-1);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        ref={buttonRef}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        className={cn(
          "px-5 py-2.5 rounded-full font-medium transition-all duration-300",
          "bg-background",
          "border-2 border-gray-200 dark:border-gray-700",
          "text-foreground",
          "shadow-sm hover:shadow-md",
          "hover:border-primary/50 dark:hover:border-primary/50",
          "hover:bg-gray-50 dark:hover:bg-gray-750",
          "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
          "focus:ring-offset-background dark:focus:ring-offset-gray-900",
          "cursor-pointer flex items-center gap-2",
          className
        )}
      >
        {selectedOption?.icon && (
          <span className="text-primary">
            {selectedOption.icon}
          </span>
        )}
        <span className="truncate">{selectedOption?.label || options[0].label}</span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn(
            "w-4 h-4 transition-transform duration-300 flex-shrink-0",
            isOpen ? 'rotate-180' : ''
          )}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          className={cn(
            "absolute right-0 mt-2 w-64 rounded-lg",
            "bg-background",
            "shadow-xl dark:shadow-gray-900/50",
            "border border-gray-200 dark:border-gray-700",
            "z-50",
            "overflow-hidden",
            "animate-in fade-in slide-in-from-top-2 duration-200"
          )}
        >
          {options.map((option, index) => (
            <button
              key={option.value}
              ref={el => { menuItemsRef.current[index] = el; }}
              onClick={() => handleOptionClick(option.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleOptionClick(option.value);
                }
              }}
              role="option"
              aria-selected={option.value === value}
              className={cn(
                "w-full text-left px-4 py-3",
                "transition-all duration-200",
                "flex items-center gap-3",
                "focus:outline-none focus:bg-gray-100 dark:focus:bg-gray-700",
                option.value === value
                  ? "bg-primary/10 text-primary dark:text-primary font-medium"
                  : "text-foreground hover:bg-gray-100 dark:hover:bg-gray-700"
              )}
            >
              {option.value === value && (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="w-4 h-4 flex-shrink-0"
                >
                  <path
                    fillRule="evenodd"
                    d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
              {option.icon && (
                <span className={cn(
                  "flex-shrink-0",
                  option.value === value ? "text-primary" : "text-gray-500 dark:text-gray-400"
                )}>
                  {option.icon}
                </span>
              )}
              <span className="truncate">{option.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}