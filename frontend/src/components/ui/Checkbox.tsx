"use client";

import { Check } from 'lucide-react';
import { forwardRef, useRef } from 'react';

interface CheckboxProps {
  id?: string;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ id, checked = false, onCheckedChange, disabled = false, className = '' }, ref) => {
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newChecked = e.target.checked;
      onCheckedChange?.(newChecked);
    };

    const inputRef = useRef<HTMLInputElement>(null);

    const handleClick = () => {
      if (!disabled && inputRef.current) {
        inputRef.current.click();
      }
    };

    return (
      <div 
        className={`relative inline-flex items-center ${className}`}
        onClick={handleClick}
        role="checkbox"
        aria-checked={checked}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleClick();
          }
        }}
      >
        <input
          ref={(node) => {
            inputRef.current = node;
            if (typeof ref === 'function') {
              ref(node);
            } else if (ref) {
              ref.current = node;
            }
          }}
          type="checkbox"
          id={id}
          checked={checked}
          onChange={handleChange}
          disabled={disabled}
          className="peer sr-only"
        />
        <div
          className={`h-5 w-5 rounded border transition-all ${
            checked
              ? 'bg-primary border-primary'
              : 'border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-800'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/20`}
        >
          {checked && (
            <div className="flex items-center justify-center h-full w-full">
              <Check className="h-3.5 w-3.5 text-white" />
            </div>
          )}
        </div>
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';
