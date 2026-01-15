"use client";

import { forwardRef, useState, useCallback, useId, useEffect } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Input');

const inputVariants = cva(
  "flex w-full rounded-lg border px-3 py-2 text-sm transition-all duration-200 file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-gray-300 bg-background focus-visible:border-primary focus-visible:ring-primary/20 dark:border-gray-600 dark:text-foreground dark:focus-visible:border-primary hover:border-gray-400 dark:hover:border-gray-500",
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

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'>,
    VariantProps<typeof inputVariants> {
  label?: string;
  error?: string;
  helperText?: string;
  success?: boolean;
  warning?: boolean;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  onClear?: () => void;
  showClearButton?: boolean;
  maxLength?: number;
  showCharCount?: boolean;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  ariaInvalid?: boolean;
  ariaErrorMessage?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({
    label,
    error,
    helperText,
    success,
    warning,
    loading = false,
    leftIcon,
    rightIcon,
    onClear,
    showClearButton = false,
    maxLength,
    showCharCount = false,
    className,
    variant,
    size,
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
    const [internalValue, setInternalValue] = useState(value || '');
    const inputId = useId();
    const errorId = useId();
    const helperId = useId();
    const charCountId = useId();

    const currentVariant = error ? 'error' : success ? 'success' : warning ? 'warning' : variant;
    const hasValue = typeof value === 'string' ? value.length > 0 : !!value;
    const displayValue = value !== undefined ? value : internalValue;
    const showClear = showClearButton && hasValue && !disabled && !loading;

    useEffect(() => {
      logger.debug('render', 'Input rendering', { 
        hasLabel: !!label, 
        hasError: !!error, 
        variant: currentVariant, 
        size,
        loading,
        disabled 
      });
    }, [label, error, currentVariant, size, loading, disabled]);

    const handleFocus = useCallback((event: React.FocusEvent<HTMLInputElement>) => {
      setIsFocused(true);
      logger.info('focus', 'Input focused', { inputId, value: displayValue });
      onFocus?.(event);
    }, [onFocus, inputId, displayValue]);

    const handleBlur = useCallback((event: React.FocusEvent<HTMLInputElement>) => {
      setIsFocused(false);
      logger.info('blur', 'Input blurred', { inputId, value: displayValue });
      onBlur?.(event);
    }, [onBlur, inputId, displayValue]);

    const handleChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = event.target.value;
      
      if (maxLength && newValue.length > maxLength) {
        logger.warn('handleChange', 'Input value exceeds maxLength', { inputId, maxLength, currentLength: newValue.length });
        return;
      }
      
      if (value === undefined) {
        setInternalValue(newValue);
      }
      
      logger.debug('handleChange', 'Input value changed', { inputId, newValue });
      onChange?.(event);
    }, [onChange, value, maxLength, inputId]);

    const handleClear = useCallback(() => {
      if (value === undefined) {
        setInternalValue('');
      }
      
      logger.info('handleClear', 'Input cleared', { inputId });
      
      const syntheticEvent = {
        target: { value: '' },
      } as React.ChangeEvent<HTMLInputElement>;
      
      onChange?.(syntheticEvent);
      onClear?.();
    }, [onChange, onClear, value, inputId]);

    const describedBy = cn(
      ariaDescribedBy,
      error && errorId,
      helperText && helperId,
      showCharCount && charCountId
    ).trim();

    const charCount = typeof displayValue === 'string' ? displayValue.length : 0;
    const remainingChars = maxLength ? maxLength - charCount : 0;
    const isNearLimit = maxLength && remainingChars <= 5 && remainingChars > 0;
    const isAtLimit = maxLength && remainingChars === 0;

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label 
            htmlFor={inputId}
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
          <input
            id={inputId}
            ref={ref}
            value={displayValue}
            onChange={handleChange}
            onFocus={handleFocus}
            onBlur={handleBlur}
            disabled={disabled || loading}
            maxLength={maxLength}
            className={cn(
              inputVariants({ variant: currentVariant, size }),
              leftIcon && "pl-10",
              (rightIcon || showClear || loading) && "pr-10",
              isFocused && "ring-2 ring-primary/20",
              className
            )}
            aria-label={ariaLabel || label}
            aria-describedby={describedBy || undefined}
            aria-invalid={ariaInvalid ?? !!error}
            aria-errormessage={ariaErrorMessage || (error ? errorId : undefined)}
            aria-required={props.required}
            aria-busy={loading}
            {...props}
          />
          {(rightIcon || showClear || loading) && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
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
                  aria-label="Clear input"
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
              {rightIcon && !loading && !showClear && (
                <div 
                  className="text-gray-400 pointer-events-none flex items-center justify-center"
                  aria-hidden="true"
                >
                  {rightIcon}
                </div>
              )}
            </div>
          )}
        </div>
        {(error || helperText || showCharCount) && (
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
            {showCharCount && maxLength && (
              <p 
                id={charCountId}
                className={cn(
                  "text-xs flex-shrink-0 transition-colors duration-200",
                  isAtLimit ? "text-red-500 dark:text-red-400" :
                  isNearLimit ? "text-yellow-500 dark:text-yellow-400" :
                  "text-gray-400 dark:text-gray-500"
                )}
                aria-live="polite"
              >
                {charCount}/{maxLength}
              </p>
            )}
          </div>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
