"use client";

import React, { forwardRef, useState, useCallback, useId, useEffect } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Select');

const selectVariants = cva(
  "flex w-full rounded-lg border px-3 py-2 text-sm transition-all duration-200 appearance-none bg-no-repeat bg-right pr-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-gray-300 bg-background focus-visible:border-primary focus-visible:ring-primary/20 dark:border-gray-600 dark:text-foreground hover:border-gray-400 dark:hover:border-gray-500",
        error: "border-red-500 bg-background focus-visible:border-red-500 focus-visible:ring-red-500/20 dark:border-red-600 dark:text-foreground",
        success: "border-green-500 bg-background focus-visible:border-green-500 focus-visible:ring-green-500/20 dark:border-green-600 dark:text-foreground",
        warning: "border-yellow-500 bg-background focus-visible:border-yellow-500 focus-visible:ring-yellow-500/20 dark:border-yellow-600 dark:text-foreground",
      },
      size: {
        sm: "h-9 px-2.5 py-1.5 text-xs",
        default: "h-10 px-3 py-2",
        lg: "h-11 px-4 py-2.5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface SelectOption {
  label: string;
  value: string | number;
  disabled?: boolean;
  group?: string;
  description?: string;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'>,
    VariantProps<typeof selectVariants> {
  label?: string;
  error?: string;
  helperText?: string;
  success?: boolean;
  warning?: boolean;
  options: SelectOption[];
  placeholder?: string;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  showClearButton?: boolean;
  onClear?: () => void;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  ariaInvalid?: boolean;
  ariaErrorMessage?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({
    label,
    error,
    helperText,
    success,
    warning,
    loading = false,
    leftIcon,
    showClearButton = false,
    onClear,
    className,
    variant,
    size,
    options,
    placeholder,
    value,
    onChange,
    onFocus,
    onBlur,
    disabled,
    ariaLabel,
    ariaDescribedBy,
    ariaInvalid,
    ariaErrorMessage,
    ...props
  }, ref) => {
    const [isFocused, setIsFocused] = useState(false);
    const selectId = useId();
    const errorId = useId();
    const helperId = useId();

    const currentVariant = error ? 'error' : success ? 'success' : warning ? 'warning' : variant;
    const hasValue = value !== undefined && value !== '';
    const showClear = showClearButton && hasValue && !disabled && !loading;

    useEffect(() => {
      logger.debug('render', 'Select rendering', { 
        hasLabel: !!label, 
        hasError: !!error, 
        variant: currentVariant, 
        size,
        loading,
        disabled,
        optionsCount: options.length 
      });
    }, [label, error, currentVariant, size, loading, disabled, options.length]);

    const handleFocus = useCallback((event: React.FocusEvent<HTMLSelectElement>) => {
      setIsFocused(true);
      logger.info('focus', 'Select focused', { selectId, value });
      onFocus?.(event);
    }, [onFocus, selectId, value]);

    const handleBlur = useCallback((event: React.FocusEvent<HTMLSelectElement>) => {
      setIsFocused(false);
      logger.info('blur', 'Select blurred', { selectId, value });
      onBlur?.(event);
    }, [onBlur, selectId, value]);

    const handleChange = useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
      const newValue = event.target.value;
      const selectedOption = options.find(opt => opt.value === newValue);
      
      logger.info('handleChange', 'Select value changed', { 
        selectId, 
        newValue, 
        label: selectedOption?.label 
      });
      
      onChange?.(event);
    }, [onChange, options, selectId]);

    const handleClear = useCallback(() => {
      logger.info('handleClear', 'Select cleared', { selectId });
      
      const syntheticEvent = {
        target: { value: '' },
      } as React.ChangeEvent<HTMLSelectElement>;
      
      onChange?.(syntheticEvent);
      onClear?.();
    }, [onChange, onClear, selectId]);

    const describedBy = cn(
      ariaDescribedBy,
      error && errorId,
      helperText && helperId
    ).trim();

    const groupedOptions = options.reduce((acc, option) => {
      const group = option.group || 'default';
      if (!acc[group]) {
        acc[group] = [];
      }
      acc[group].push(option);
      return acc;
    }, {} as Record<string, SelectOption[]>);

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label 
            htmlFor={selectId}
            className={cn(
              "text-sm font-medium transition-colors duration-200",
              error ? "text-red-600 dark:text-red-400" :
              success ? "text-green-600 dark:text-green-400" :
              warning ? "text-yellow-600 dark:text-yellow-400" :
              "text-gray-700 dark:text-gray-300"
            )}
          >
            {label}
            {props.required && <span className="text-red-500 ml-1" aria-label="required">*</span>}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div 
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none flex items-center justify-center"
              aria-hidden="true"
            >
              {leftIcon}
            </div>
          )}
          <select
            id={selectId}
            ref={ref}
            value={value}
            onChange={handleChange}
            onFocus={handleFocus}
            onBlur={handleBlur}
            disabled={disabled || loading}
            className={cn(
              selectVariants({ variant: currentVariant, size }),
              leftIcon && "pl-10",
              (showClear || loading) && "pr-20",
              !showClear && !loading && "pr-10",
              isFocused && "ring-2 ring-primary/20",
              "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 fill=%22none%22 viewBox=%220 0 20 20%22%3E%3Cpath stroke=%22%236b7280%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 stroke-width=%221.5%22 d=%22M6 8l4 4 4-4%22/%3E%3C/svg%3E')] dark:bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 fill=%22none%22 viewBox=%220 0 20 20%22%3E%3Cpath stroke=%22%239ca3af%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 stroke-width=%221.5%22 d=%22M6 8l4 4 4-4%22/%3E%3C/svg%3E')]",
              className
            )}
            aria-label={ariaLabel || label}
            aria-describedby={describedBy || undefined}
            aria-invalid={ariaInvalid ?? !!error}
            aria-errormessage={ariaErrorMessage || (error ? errorId : undefined)}
            aria-required={props.required}
            aria-busy={loading}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {Object.entries(groupedOptions).map(([group, groupOptions]) => (
              <React.Fragment key={group}>
                {group !== 'default' && (
                  <optgroup label={group}>
                    {groupOptions.map((option) => (
                      <option
                        key={option.value}
                        value={option.value}
                        disabled={option.disabled}
                      >
                        {option.label}
                        {option.description && ` - ${option.description}`}
                      </option>
                    ))}
                  </optgroup>
                )}
                {group === 'default' && groupOptions.map((option) => (
                  <option
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                  >
                    {option.label}
                    {option.description && ` - ${option.description}`}
                  </option>
                ))}
              </React.Fragment>
            ))}
          </select>
          {(showClear || loading) && (
            <div className="absolute right-8 top-1/2 -translate-y-1/2 flex items-center">
              {loading && (
                <div 
                  className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"
                  aria-hidden="true"
                  role="status"
                  aria-label="Loading"
                />
              )}
              {showClear && !loading && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/50 rounded p-0.5"
                  aria-label="Clear selection"
                  tabIndex={0}
                >
                  <svg 
                    className="w-4 h-4" 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          )}
        </div>
        {(error || helperText) && (
          <div className="flex justify-between items-start gap-2">
            <div className="flex-1">
              {error && (
                <p 
                  id={errorId}
                  className="text-xs text-red-500 dark:text-red-400 flex items-center gap-1"
                  role="alert"
                  aria-live="polite"
                >
                  <svg 
                    className="w-3 h-3 flex-shrink-0" 
                    fill="currentColor" 
                    viewBox="0 0 20 20"
                    aria-hidden="true"
                  >
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  {error}
                </p>
              )}
              {helperText && !error && (
                <p 
                  id={helperId}
                  className="text-xs text-gray-500 dark:text-gray-400"
                >
                  {helperText}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }
);

Select.displayName = "Select";
