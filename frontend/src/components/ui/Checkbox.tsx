"use client";

import { Check, Minus } from 'lucide-react';
import { forwardRef, useRef, type ChangeEvent, type KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Checkbox');

export type CheckboxState = boolean | 'indeterminate';

export interface CheckboxProps {
  id?: string;
  checked?: CheckboxState;
  onCheckedChange?: (checked: CheckboxState) => void;
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  indeterminate?: boolean;
  size?: 'sm' | 'default' | 'lg';
}

const sizeStyles = {
  sm: 'h-4 w-4',
  default: 'h-5 w-5',
  lg: 'h-6 w-6',
};

const iconSizes = {
  sm: 'h-3 w-3',
  default: 'h-3.5 w-3.5',
  lg: 'h-4 w-4',
};

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({
    id,
    checked = false,
    onCheckedChange,
    disabled = false,
    className = '',
    ariaLabel,
    ariaDescribedBy,
    indeterminate = false,
    size = 'default',
  }, ref) => {
    const inputRef = useRef<HTMLInputElement>(null);

    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
      if (disabled) {
        logger.warn('handleChange', 'Checkbox change prevented - disabled');
        return;
      }

      const newChecked = e.target.checked;
      logger.info('handleChange', 'Checkbox changed', { newChecked, indeterminate });
      onCheckedChange?.(newChecked);
    };

    const handleClick = () => {
      if (!disabled && inputRef.current) {
        inputRef.current.click();
      }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
      if (disabled) {
        return;
      }

      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleClick();
      }
    };

    const isChecked = checked === true;
    const isIndeterminate = indeterminate || checked === 'indeterminate';
    const ariaChecked = isIndeterminate ? 'mixed' : isChecked;

    return (
      <div
        className={cn(
          "relative inline-flex items-center",
          disabled && "opacity-50 cursor-not-allowed",
          !disabled && "cursor-pointer",
          className
        )}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        role="checkbox"
        aria-checked={ariaChecked}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        tabIndex={disabled ? -1 : 0}
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
          checked={isChecked}
          onChange={handleChange}
          disabled={disabled}
          className="peer sr-only"
          aria-hidden="true"
        />
        <div
          className={cn(
            "rounded border transition-all duration-200",
            "peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-offset-2 peer-focus:ring-primary/20",
            "active:scale-95",
            sizeStyles[size],
            isChecked
              ? 'bg-primary border-primary'
              : 'border-gray-300 bg-background dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500',
            disabled && "cursor-not-allowed"
          )}
        >
          {isChecked && (
            <div className="flex items-center justify-center h-full w-full">
              <Check className={cn("text-white", iconSizes[size])} aria-hidden="true" />
            </div>
          )}
          {isIndeterminate && !isChecked && (
            <div className="flex items-center justify-center h-full w-full">
              <Minus className={cn("text-white", iconSizes[size])} aria-hidden="true" />
            </div>
          )}
        </div>
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';
