"use client";

import React, { forwardRef, useState, useCallback, useId, useEffect, useMemo } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Tabs');

const tabsListVariants = cva(
  "flex items-center gap-2 transition-all duration-200",
  {
    variants: {
      variant: {
        default: "border-b border-gray-200 dark:border-gray-700",
        pills: "border-b-0",
        underline: "border-b border-gray-200 dark:border-gray-700",
      },
      size: {
        sm: "",
        default: "",
        lg: "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const tabsTriggerVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-b-2 border-transparent hover:border-gray-300 dark:hover:border-gray-600 data-[state=active]:border-primary data-[state=active]:text-primary dark:data-[state=active]:border-primary",
        pills: "rounded-md px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 data-[state=active]:bg-primary data-[state=active]:text-foreground",
        underline: "border-b-2 border-transparent hover:border-gray-300 dark:hover:border-gray-600 data-[state=active]:border-primary data-[state=active]:text-primary",
      },
      size: {
        sm: "px-3 py-1.5 text-xs",
        default: "px-4 py-2 text-sm",
        lg: "px-6 py-3 text-base",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface TabsProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  children: React.ReactNode;
  className?: string;
  variant?: VariantProps<typeof tabsListVariants>['variant'];
  size?: VariantProps<typeof tabsTriggerVariants>['size'];
  ariaLabel?: string;
}

export const Tabs = forwardRef<HTMLDivElement, TabsProps<string>>(
  ({ value, onChange, children, className, variant, size, ariaLabel, ...props }, ref) => {
    const tabsId = useId();

    useEffect(() => {
      logger.debug('render', 'Tabs rendering', { 
        currentValue: value, 
        variant, 
        size,
        childrenCount: React.Children.count(children) 
      });
    }, [value, variant, size, children]);

    const contextValue = useMemo(() => ({
      value,
      onChange,
      variant,
      size,
      tabsId,
    }), [value, onChange, variant, size, tabsId]);

    return (
      <TabsContext.Provider value={contextValue}>
        <div
          ref={ref}
          role="tablist"
          aria-label={ariaLabel || 'Tabs'}
          aria-orientation="horizontal"
          className={cn("w-full", className)}
          {...props}
        >
          {children}
        </div>
      </TabsContext.Provider>
    );
  }
);

Tabs.displayName = "Tabs";

export interface TabsListProps {
  children: React.ReactNode;
  className?: string;
}

export const TabsList = forwardRef<HTMLDivElement, TabsListProps>(
  ({ children, className, ...props }, ref) => {
    const context = useTabsContext();

    return (
      <div
        ref={ref}
        role="presentation"
        className={cn(
          tabsListVariants({ variant: context.variant, size: context.size }),
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

TabsList.displayName = "TabsList";

export interface TabsTriggerProps<T extends string> {
  value: T;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  icon?: React.ReactNode;
  badge?: number | string;
  ariaLabel?: string;
}

export const TabsTrigger = forwardRef<HTMLButtonElement, TabsTriggerProps<string>>(
  ({ value, children, className, disabled = false, icon, badge, ariaLabel, ...props }, ref) => {
    const context = useTabsContext();
    const [isFocused, setIsFocused] = useState(false);
    const triggerId = useId();

    const isSelected = context.value === value;

    useEffect(() => {
      logger.debug('render', 'TabsTrigger rendering', { 
        value, 
        isSelected, 
        disabled,
        hasIcon: !!icon,
        hasBadge: !!badge 
      });
    }, [value, isSelected, disabled, icon, badge]);

    const handleClick = useCallback(() => {
      if (disabled) {
        logger.warn('handleClick', 'TabsTrigger click prevented', { value, disabled });
        return;
      }

      logger.info('handleClick', 'TabsTrigger clicked', { value, previousValue: context.value });
      context.onChange(value);
    }, [disabled, value, context]);

    const handleFocus = useCallback(() => {
      setIsFocused(true);
      logger.debug('focus', 'TabsTrigger focused', { value, isSelected });
    }, [value, isSelected]);

    const handleBlur = useCallback(() => {
      setIsFocused(false);
      logger.debug('blur', 'TabsTrigger blurred', { value, isSelected });
    }, [value, isSelected]);

    const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>) => {
      const triggers = Array.from(
        document.querySelectorAll('[role="tab"][data-tabs-id]')
      ) as HTMLButtonElement[];
      
      let currentIndex = -1;
      if (ref && typeof ref !== 'function' && ref.current) {
        currentIndex = triggers.findIndex(t => t === ref.current);
      }
      
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault();
        const direction = event.key === 'ArrowRight' ? 1 : -1;
        const nextIndex = (currentIndex + direction + triggers.length) % triggers.length;
        triggers[nextIndex]?.focus();
        triggers[nextIndex]?.click();
      }
      
      if (event.key === 'Home') {
        event.preventDefault();
        triggers[0]?.focus();
        triggers[0]?.click();
      }
      
      if (event.key === 'End') {
        event.preventDefault();
        triggers[triggers.length - 1]?.focus();
        triggers[triggers.length - 1]?.click();
      }
    }, [ref]);

    return (
      <button
        ref={ref}
        id={triggerId}
        type="button"
        role="tab"
        aria-selected={isSelected}
        aria-controls={`${context.tabsId}-panel-${value}`}
        aria-disabled={disabled}
        disabled={disabled}
        data-tabs-id={context.tabsId}
        onClick={handleClick}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        className={cn(
          tabsTriggerVariants({ variant: context.variant, size: context.size }),
          isSelected && "data-[state=active]",
          disabled && "opacity-50 cursor-not-allowed",
          isFocused && "ring-2 ring-primary/20",
          className
        )}
        aria-label={ariaLabel}
        {...props}
      >
        {icon && (
          <span className="mr-2" aria-hidden="true">
            {icon}
          </span>
        )}
        <span className="relative">
          {children}
          {badge !== undefined && (
            <span 
              className={cn(
                "absolute -top-2 -right-3 flex h-5 w-5 items-center justify-center rounded-full text-xs font-medium",
                isSelected 
                  ? "bg-primary text-foreground" 
                  : "bg-gray-200 text-foreground dark:bg-gray-700"
              )}
              aria-label={`${badge} items`}
            >
              {typeof badge === 'number' && badge > 99 ? '99+' : badge}
            </span>
          )}
        </span>
      </button>
    );
  }
);

TabsTrigger.displayName = "TabsTrigger";

export interface TabsContentProps<T extends string> {
  value: T;
  children: React.ReactNode;
  className?: string;
  forceMount?: boolean;
}

export const TabsContent = forwardRef<HTMLDivElement, TabsContentProps<string>>(
  ({ value, children, className, forceMount = false, ...props }, ref) => {
    const context = useTabsContext();
    const isVisible = context.value === value;

    if (!forceMount && context.value !== value) {
      return null;
    }

    return (
      <div
        ref={ref}
        id={`${context.tabsId}-panel-${value}`}
        role="tabpanel"
        aria-labelledby={`${context.tabsId}-tab-${value}`}
        hidden={forceMount && !isVisible}
        className={cn(
          "mt-4 transition-opacity duration-200",
          isVisible ? "opacity-100" : "opacity-0",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

TabsContent.displayName = "TabsContent";

interface TabsContextValue {
  value: string;
  onChange: (value: string) => void;
  variant?: VariantProps<typeof tabsListVariants>['variant'];
  size?: VariantProps<typeof tabsTriggerVariants>['size'];
  tabsId: string;
}

const TabsContext = React.createContext<TabsContextValue | undefined>(undefined);

function useTabsContext(): TabsContextValue {
  const context = React.useContext(TabsContext);
  if (!context) {
    throw new Error('Tabs components must be used within a Tabs component');
  }
  return context;
}
