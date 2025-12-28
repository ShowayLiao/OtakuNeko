"use client";

import { ReactNode } from 'react';

interface TabsProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  children: ReactNode;
}

export function Tabs<T extends string>({ children }: Omit<TabsProps<T>, 'value' | 'onChange'>) {
  return (
    <div className="w-full">
      {children}
    </div>
  );
}

interface TabsListProps {
  children: ReactNode;
}

export function TabsList({ children }: TabsListProps) {
  return (
    <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
      {children}
    </div>
  );
}

interface TabsTriggerProps<T extends string> {
  value: T;
  selectedValue: T;
  onClick: () => void;
  children: ReactNode;
}

export function TabsTrigger<T extends string>({ value, selectedValue, onClick, children }: TabsTriggerProps<T>) {
  const isSelected = value === selectedValue;
  
  return (
    <button
      onClick={onClick}
      className={`
        px-4 py-2 text-sm font-medium transition-colors relative
        ${isSelected 
          ? 'text-primary dark:text-primary' 
          : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200'
        }
      `}
    >
      {children}
      {isSelected && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary dark:bg-primary" />
      )}
    </button>
  );
}

interface TabsContentProps<T extends string> {
  value: T;
  selectedValue: T;
  children: ReactNode;
}

export function TabsContent<T extends string>({ value, selectedValue, children }: TabsContentProps<T>) {
  if (value !== selectedValue) return null;
  
  return (
    <div className="mt-4">
      {children}
    </div>
  );
}
