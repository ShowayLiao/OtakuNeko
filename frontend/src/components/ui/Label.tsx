"use client";

import { forwardRef, useState, useCallback, useId, useEffect } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Label');

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 transition-all duration-200",
  {
    variants: {
      variant: {
        default: "text-foreground dark:text-gray-300",
        muted: "text-gray-500 dark:text-gray-400",
        error: "text-red-600 dark:text-red-400",
        success: "text-green-600 dark:text-green-400",
        warning: "text-yellow-600 dark:text-yellow-400",
      },
      size: {
        sm: "text-xs",
        default: "text-sm",
        lg: "text-base",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface LabelProps
  extends Omit<React.LabelHTMLAttributes<HTMLLabelElement>, 'size'>,
    VariantProps<typeof labelVariants> {
  children: React.ReactNode;
  required?: boolean;
  optional?: boolean;
  helperText?: string;
  errorText?: string;
  showTooltip?: boolean;
  tooltipContent?: string;
  onClick?: () => void;
}

export const Label = forwardRef<HTMLLabelElement, LabelProps>(
  ({
    className,
    variant,
    size,
    required,
    optional,
    helperText,
    errorText,
    showTooltip = false,
    tooltipContent,
    onClick,
    children,
    htmlFor,
    id,
    ...props
  }, ref) => {
    const labelId = useId();
    const tooltipId = useId();
    const [isTooltipVisible, setIsTooltipVisible] = useState(false);

    const currentVariant = errorText ? 'error' : variant;
    const finalId = id || labelId;

    useEffect(() => {
      logger.debug('render', 'Label rendering', { 
        variant: currentVariant, 
        size,
        required,
        optional,
        hasHelperText: !!helperText,
        hasErrorText: !!errorText,
        hasTooltip: showTooltip
      });
    }, [currentVariant, size, required, optional, helperText, errorText, showTooltip]);

    const handleClick = useCallback(() => {
      logger.info('click', 'Label clicked', { labelId: finalId, htmlFor });
      onClick?.();
    }, [onClick, finalId, htmlFor]);

    const handleMouseEnter = useCallback(() => {
      if (showTooltip && tooltipContent) {
        setIsTooltipVisible(true);
        logger.debug('tooltip', 'Tooltip shown', { labelId: finalId });
      }
    }, [showTooltip, tooltipContent, finalId]);

    const handleMouseLeave = useCallback(() => {
      if (showTooltip) {
        setIsTooltipVisible(false);
        logger.debug('tooltip', 'Tooltip hidden', { labelId: finalId });
      }
    }, [showTooltip, finalId]);

    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1 relative">
          <label
            ref={ref}
            id={finalId}
            htmlFor={htmlFor}
            className={cn(
              labelVariants({ variant: currentVariant, size }),
              "cursor-pointer select-none",
              onClick && "hover:opacity-80",
              className
            )}
            onClick={handleClick}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            aria-required={required}
            aria-invalid={!!errorText}
            {...props}
          >
            {children}
          </label>
          {required && (
            <span 
              className="text-red-500 ml-0.5" 
              aria-label="required"
              role="presentation"
            >
              *
            </span>
          )}
          {optional && !required && (
            <span 
              className="text-gray-400 text-xs ml-1" 
              aria-label="optional"
            >
              (optional)
            </span>
          )}
          {showTooltip && tooltipContent && (
            <div 
              className="relative inline-block"
              onMouseEnter={handleMouseEnter}
              onMouseLeave={handleMouseLeave}
              tabIndex={0}
              role="button"
              aria-label="Show tooltip"
              aria-describedby={isTooltipVisible ? tooltipId : undefined}
            >
              <svg 
                className="w-4 h-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors cursor-help"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {isTooltipVisible && (
                <div 
                  id={tooltipId}
                  className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg z-50 whitespace-nowrap max-w-xs"
                  role="tooltip"
                  aria-live="polite"
                >
                  {tooltipContent}
                </div>
              )}
            </div>
          )}
        </div>
        {helperText && !errorText && (
          <p 
            className="text-xs text-gray-500 dark:text-gray-400"
            id={`${finalId}-helper`}
          >
            {helperText}
          </p>
        )}
        {errorText && (
          <p 
            className="text-xs text-red-500 dark:text-red-400 flex items-center gap-1"
            id={`${finalId}-error`}
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
            {errorText}
          </p>
        )}
      </div>
    );
  }
);

Label.displayName = "Label";
