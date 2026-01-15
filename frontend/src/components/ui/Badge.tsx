"use client";

import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Badge');

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        default: "bg-gray-100 text-foreground dark:bg-gray-800 dark:text-gray-300",
        success: "bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400",
        warning: "bg-yellow-50 text-yellow-600 dark:bg-yellow-900/20 dark:text-yellow-400",
        destructive: "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400",
        info: "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400",
        outline: "border border-gray-200 bg-transparent text-foreground dark:border-gray-700 dark:text-gray-300",
      },
      size: {
        default: "px-2.5 py-1 text-xs",
        sm: "px-2 py-0.5 text-[10px]",
        lg: "px-3 py-1.5 text-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface BadgeProps
  extends Omit<HTMLAttributes<HTMLSpanElement>, 'size' | 'variant'>,
    VariantProps<typeof badgeVariants> {
  children: ReactNode;
  showDot?: boolean;
  dotColor?: string;
  ariaLabel?: string;
  role?: string;
}

const DOT_COLORS: Record<NonNullable<VariantProps<typeof badgeVariants>['variant']>, string> = {
  default: "bg-gray-600 dark:bg-gray-400",
  success: "bg-green-600 dark:bg-green-400",
  warning: "bg-yellow-600 dark:bg-yellow-400",
  destructive: "bg-red-600 dark:bg-red-400",
  info: "bg-blue-600 dark:bg-blue-400",
  outline: "bg-gray-600 dark:bg-gray-400",
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({
    className,
    variant,
    size,
    showDot = true,
    dotColor,
    children,
    ariaLabel,
    role = "status",
    ...props
  }, ref) => {
    const currentVariant = variant || "default";
    const dotClassName = dotColor || DOT_COLORS[currentVariant];

    logger.debug('render', 'Badge rendering', { variant: currentVariant, size, showDot });

    return (
      <span
        ref={ref}
        className={cn(badgeVariants({ variant, size, className }))}
        aria-label={ariaLabel}
        role={role}
        {...props}
      >
        {showDot && (
          <span
            className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", dotClassName)}
            aria-hidden="true"
          />
        )}
        <span className="truncate">{children}</span>
      </span>
    );
  }
);

Badge.displayName = 'Badge';
