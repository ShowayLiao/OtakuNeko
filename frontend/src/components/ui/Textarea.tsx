"use client";

import { forwardRef, useState, useCallback, useEffect, useId, useMemo } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Textarea');

const textareaVariants = cva(
  "flex w-full rounded-lg border px-3 py-2 text-sm transition-all duration-200 placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-gray-300 bg-background focus-visible:border-primary focus-visible:ring-primary/20 dark:border-gray-600 dark:text-foreground",
        error: "border-red-500 bg-background focus-visible:border-red-500 focus-visible:ring-red-500/20 dark:border-red-600 dark:text-foreground",
        success: "border-green-500 bg-background focus-visible:border-green-500 focus-visible:ring-green-500/20 dark:border-green-600 dark:text-foreground",
        warning: "border-yellow-500 bg-background focus-visible:border-yellow-500 focus-visible:ring-yellow-500/20 dark:border-yellow-600 dark:text-foreground",
      },
      size: {
        sm: "px-2 py-1.5 text-xs min-h-[60px]",
        default: "px-3 py-2 text-sm min-h-[80px]",
        lg: "px-4 py-3 text-base min-h-[120px]",
      },
      resize: {
        none: "resize-none",
        vertical: "resize-y",
        horizontal: "resize-x",
        both: "resize",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      resize: "none",
    },
  }
);

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement>,
    VariantProps<typeof textareaVariants> {
  label?: string;
  error?: string;
  helperText?: string;
  loading?: boolean;
  showCharCount?: boolean;
  maxLength?: number;
  clearable?: boolean;
  onClear?: () => void;
  ariaLabel?: string;
  ariaDescribedBy?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({
    label,
    error,
    helperText,
    loading = false,
    showCharCount = false,
    maxLength,
    clearable = false,
    onClear,
    className,
    variant,
    size,
    resize,
    value,
    onChange,
    onFocus,
    onBlur,
    ariaLabel,
    ariaDescribedBy,
    ...props
  }, ref) => {
    const [isFocused, setIsFocused] = useState(false);
    const textareaId = useId();
    const errorId = useId();
    const helperTextId = useId();
    const charCountId = useId();

    const actualVariant = error ? "error" : variant;
    const isDisabled = props.disabled || loading;

    useEffect(() => {
      const valueLength = typeof value === 'string' ? value.length : 0;
      logger.debug('render', 'Textarea rendering', { 
        label,
        variant: actualVariant,
        size,
        resize,
        loading,
        disabled: props.disabled,
        hasValue: !!value,
        valueLength,
        maxLength,
        showCharCount,
        clearable
      });
    }, [label, actualVariant, size, resize, loading, props.disabled, value, maxLength, showCharCount, clearable]);

    const handleChange = useCallback((event: React.ChangeEvent<HTMLTextAreaElement>) => {
      logger.debug('handleChange', 'Textarea value changed', { 
        textareaId, 
        newValueLength: event.target.value.length 
      });
      onChange?.(event);
    }, [onChange, textareaId]);

    const handleFocus = useCallback((event: React.FocusEvent<HTMLTextAreaElement>) => {
      setIsFocused(true);
      logger.debug('handleFocus', 'Textarea focused', { textareaId, label });
      onFocus?.(event);
    }, [onFocus, textareaId, label]);

    const handleBlur = useCallback((event: React.FocusEvent<HTMLTextAreaElement>) => {
      setIsFocused(false);
      logger.debug('handleBlur', 'Textarea blurred', { textareaId, label });
      onBlur?.(event);
    }, [onBlur, textareaId, label]);

    const handleClear = useCallback(() => {
      logger.info('handleClear', 'Textarea cleared', { textareaId, label });
      onClear?.();
    }, [onClear, textareaId, label]);

    const ariaDescribedByParts = useMemo(() => {
      const parts: string[] = [];
      if (error) parts.push(errorId);
      if (helperText) parts.push(helperTextId);
      if (showCharCount) parts.push(charCountId);
      if (ariaDescribedBy) parts.push(ariaDescribedBy);
      return parts.length > 0 ? parts.join(' ') : undefined;
    }, [error, helperText, showCharCount, ariaDescribedBy, errorId, helperTextId, charCountId]);

    const currentLength = value?.toString().length || 0;
    const showClearButton = clearable && !isDisabled && currentLength > 0;

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label 
            htmlFor={textareaId}
            className={cn(
              "text-sm font-medium transition-colors",
              error ? "text-red-600 dark:text-red-400" : "text-gray-700 dark:text-gray-300",
              isFocused && !error && "text-primary dark:text-primary"
            )}
          >
            {label}
          </label>
        )}
        <div className="relative">
          <textarea
            ref={ref}
            id={textareaId}
            value={value}
            onChange={handleChange}
            onFocus={handleFocus}
            onBlur={handleBlur}
            maxLength={maxLength}
            disabled={isDisabled}
            aria-label={ariaLabel || label}
            aria-invalid={!!error}
            aria-describedby={ariaDescribedByParts}
            aria-required={props.required}
            className={cn(
              textareaVariants({ variant: actualVariant, size, resize }),
              isFocused && "ring-2 ring-primary/20",
              loading && "animate-pulse",
              className
            )}
            {...props}
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <svg 
                className="animate-spin h-4 w-4 text-gray-400" 
                xmlns="http://www.w3.org/2000/svg" 
                fill="none" 
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle 
                  className="opacity-25" 
                  cx="12" 
                  cy="12" 
                  r="10" 
                  stroke="currentColor" 
                  strokeWidth="4"
                />
                <path 
                  className="opacity-75" 
                  fill="currentColor" 
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            </div>
          )}
          {showClearButton && !loading && (
            <button
              type="button"
              onClick={handleClear}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/50 rounded p-1"
              aria-label="Clear input"
              tabIndex={-1}
            >
              <svg 
                className="h-4 w-4" 
                xmlns="http://www.w3.org/2000/svg" 
                fill="none" 
                viewBox="0 0 24 24" 
                stroke="currentColor"
                aria-hidden="true"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={2} 
                  d="M6 18L18 6M6 6l12 12" 
                />
              </svg>
            </button>
          )}
        </div>
        {(error || helperText || showCharCount) && (
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1">
              {error && (
                <p 
                  id={errorId}
                  className="text-xs text-red-500 dark:text-red-400 flex items-center gap-1"
                  role="alert"
                >
                  <svg 
                    className="h-3 w-3" 
                    xmlns="http://www.w3.org/2000/svg" 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path 
                      strokeLinecap="round" 
                      strokeLinejoin="round" 
                      strokeWidth={2} 
                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" 
                    />
                  </svg>
                  {error}
                </p>
              )}
              {!error && helperText && (
                <p 
                  id={helperTextId}
                  className="text-xs text-gray-500 dark:text-gray-400"
                >
                  {helperText}
                </p>
              )}
            </div>
            {showCharCount && maxLength && (
              <p 
                id={charCountId}
                className={cn(
                  "text-xs transition-colors",
                  currentLength > maxLength 
                    ? "text-red-500 dark:text-red-400" 
                    : "text-gray-500 dark:text-gray-400"
                )}
                aria-live="polite"
              >
                {currentLength}/{maxLength}
              </p>
            )}
          </div>
        )}
      </div>
    );
  }
);

Textarea.displayName = "Textarea";
