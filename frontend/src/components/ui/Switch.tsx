"use client";

import { forwardRef, useState, useCallback, useId, useEffect } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Switch');

const switchVariants = cva(
  "relative inline-flex items-center rounded-full transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "",
        success: "",
        warning: "",
        danger: "",
      },
      size: {
        sm: "h-5 w-9",
        default: "h-6 w-11",
        lg: "h-7 w-13",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const thumbVariants = cva(
  "inline-block transform rounded-full bg-background shadow-sm transition-all duration-200 pointer-events-none",
  {
    variants: {
      size: {
        sm: "h-3 w-3",
        default: "h-4 w-4",
        lg: "h-5 w-5",
      },
    },
    defaultVariants: {
      size: "default",
    },
  }
);

export interface SwitchProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'size' | 'onChange' | 'checked'>,
    VariantProps<typeof switchVariants> {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  description?: string;
  loading?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
  ariaDescribedBy?: string;
}

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(
  ({
    checked,
    onChange,
    label,
    description,
    loading = false,
    disabled = false,
    className,
    variant,
    size,
    onClick,
    onFocus,
    onBlur,
    ariaLabel,
    ariaDescribedBy,
    ...props
  }, ref) => {
    const [isFocused, setIsFocused] = useState(false);
    const [isPressed, setIsPressed] = useState(false);
    const switchId = useId();
    const descriptionId = useId();

    const isDisabled = disabled || loading;

    useEffect(() => {
      logger.debug('render', 'Switch rendering', { 
        checked, 
        variant, 
        size,
        loading,
        disabled,
        hasLabel: !!label,
        hasDescription: !!description
      });
    }, [checked, variant, size, loading, disabled, label, description]);

    const handleClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
      if (isDisabled) {
        logger.warn('handleClick', 'Switch click prevented', { isDisabled });
        return;
      }

      const newValue = !checked;
      logger.info('handleClick', 'Switch toggled', { switchId, oldValue: checked, newValue });
      onChange(newValue);
      onClick?.(event);
    }, [checked, onChange, isDisabled, onClick, switchId]);

    const handleFocus = useCallback((event: React.FocusEvent<HTMLButtonElement>) => {
      setIsFocused(true);
      logger.debug('focus', 'Switch focused', { switchId, checked });
      onFocus?.(event);
    }, [onFocus, switchId, checked]);

    const handleBlur = useCallback((event: React.FocusEvent<HTMLButtonElement>) => {
      setIsFocused(false);
      logger.debug('blur', 'Switch blurred', { switchId, checked });
      onBlur?.(event);
    }, [onBlur, switchId, checked]);

    const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handleClick(event as unknown as React.MouseEvent<HTMLButtonElement>);
      }
    }, [handleClick]);

    const getTrackColor = () => {
      if (isDisabled) {
        return 'bg-gray-300 dark:bg-gray-600';
      }
      
      if (checked) {
        switch (variant) {
          case 'success':
            return 'bg-green-500 dark:bg-green-600';
          case 'warning':
            return 'bg-yellow-500 dark:bg-yellow-600';
          case 'danger':
            return 'bg-red-500 dark:bg-red-600';
          default:
            return 'bg-primary dark:bg-primary';
        }
      }
      
      return 'bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500';
    };

    const getThumbPosition = () => {
      switch (size) {
        case 'sm':
          return checked ? 'translate-x-5' : 'translate-x-0.5';
        case 'lg':
          return checked ? 'translate-x-7' : 'translate-x-1';
        default:
          return checked ? 'translate-x-6' : 'translate-x-1';
      }
    };

    const getRingColor = () => {
      if (isFocused) {
        switch (variant) {
          case 'success':
            return 'focus:ring-green-500/50';
          case 'warning':
            return 'focus:ring-yellow-500/50';
          case 'danger':
            return 'focus:ring-red-500/50';
          default:
            return 'focus:ring-primary/50';
        }
      }
      return '';
    };

    return (
      <div className="flex items-center gap-3">
        <button
          ref={ref}
          id={switchId}
          type="button"
          role="switch"
          aria-checked={checked}
          aria-label={ariaLabel || label}
          aria-describedby={description ? descriptionId : ariaDescribedBy}
          aria-disabled={isDisabled}
          aria-busy={loading}
          disabled={isDisabled}
          onClick={handleClick}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          onMouseDown={() => setIsPressed(true)}
          onMouseUp={() => setIsPressed(false)}
          onMouseLeave={() => setIsPressed(false)}
          className={cn(
            switchVariants({ variant, size }),
            getTrackColor(),
            getRingColor(),
            isPressed && 'scale-95',
            className
          )}
          {...props}
        >
          <span
            className={cn(
              thumbVariants({ size }),
              getThumbPosition()
            )}
            aria-hidden="true"
          />
          {loading && (
            <div 
              className="absolute inset-0 flex items-center justify-center"
              aria-hidden="true"
            >
              <div 
                className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"
                role="status"
                aria-label="Loading"
              />
            </div>
          )}
        </button>
        {(label || description) && (
          <div className="flex flex-col gap-0.5">
            {label && (
              <span 
                className={cn(
                  "text-sm font-medium transition-colors duration-200",
                  isDisabled ? "text-gray-400 dark:text-gray-500" : "text-foreground dark:text-gray-300"
                )}
              >
                {label}
              </span>
            )}
            {description && (
              <span 
                id={descriptionId}
                className={cn(
                  "text-xs transition-colors duration-200",
                  isDisabled ? "text-gray-400 dark:text-gray-500" : "text-foreground dark:text-gray-400"
                )}
              >
                {description}
              </span>
            )}
          </div>
        )}
      </div>
    );
  }
);

Switch.displayName = "Switch";
