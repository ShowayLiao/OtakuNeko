"use client";

import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Card');

const cardVariants = cva(
  "rounded-xl border bg-background shadow-sm transition-all duration-200",
  {
    variants: {
      variant: {
        default: "border-gray-200 dark:border-gray-800",
        elevated: "border-gray-200 dark:border-gray-800 shadow-md hover:shadow-lg",
        outlined: "border-2 border-gray-300 dark:border-gray-700",
        ghost: "border-transparent bg-transparent shadow-none hover:bg-gray-50 dark:hover:bg-gray-800/50",
      },
      size: {
        default: "",
        sm: "p-3",
        md: "p-4",
        lg: "p-6",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface CardProps
  extends Omit<HTMLAttributes<HTMLDivElement>, 'size' | 'variant'>,
    VariantProps<typeof cardVariants> {
  children: ReactNode;
  hoverable?: boolean;
  clickable?: boolean;
  onClick?: () => void;
  ariaLabel?: string;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({
    className,
    variant,
    size,
    children,
    hoverable = false,
    clickable = false,
    onClick,
    ariaLabel,
    ...props
  }, ref) => {
    const handleClick = () => {
      if (clickable && onClick) {
        logger.info('handleClick', 'Card clicked', { variant, size });
        onClick();
      }
    };

    const interactiveProps = clickable
      ? {
          onClick: handleClick,
          role: "button",
          tabIndex: 0,
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleClick();
            }
          },
        }
      : {};

    return (
      <div
        ref={ref}
        className={cn(
          cardVariants({ variant, size }),
          hoverable && "hover:shadow-md hover:border-gray-300 dark:hover:border-gray-700",
          clickable && "cursor-pointer active:scale-[0.99]",
          className
        )}
        aria-label={ariaLabel}
        {...interactiveProps}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

export interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ className, children, ...props }, ref) => {
    logger.debug('render', 'CardHeader rendering');
    return (
      <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props}>
        {children}
      </div>
    );
  }
);

CardHeader.displayName = 'CardHeader';

export interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  children: ReactNode;
  level?: 1 | 2 | 3 | 4 | 5 | 6;
}

export const CardTitle = forwardRef<HTMLHeadingElement, CardTitleProps>(
  ({ className, children, level = 3, ...props }, ref) => {
    const headingTags: Record<number, React.ElementType> = {
      1: 'h1',
      2: 'h2',
      3: 'h3',
      4: 'h4',
      5: 'h5',
      6: 'h6',
    };
    const HeadingTag = headingTags[level];
    logger.debug('render', 'CardTitle rendering', { level });
    return (
      <HeadingTag
        ref={ref}
        className={cn("text-lg font-semibold leading-none tracking-tight text-foreground", className)}
        {...props}
      >
        {children}
      </HeadingTag>
    );
  }
);

CardTitle.displayName = 'CardTitle';

export interface CardDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {
  children: ReactNode;
}

export const CardDescription = forwardRef<HTMLParagraphElement, CardDescriptionProps>(
  ({ className, children, ...props }, ref) => {
    logger.debug('render', 'CardDescription rendering');
    return (
      <p ref={ref} className={cn("text-sm text-gray-500 dark:text-gray-400", className)} {...props}>
        {children}
      </p>
    );
  }
);

CardDescription.displayName = 'CardDescription';

export interface CardContentProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const CardContent = forwardRef<HTMLDivElement, CardContentProps>(
  ({ className, children, ...props }, ref) => {
    logger.debug('render', 'CardContent rendering');
    return (
      <div ref={ref} className={cn("p-6 pt-0", className)} {...props}>
        {children}
      </div>
    );
  }
);

CardContent.displayName = 'CardContent';

export interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  align?: 'left' | 'center' | 'right' | 'space-between';
}

export const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ className, children, align = 'left', ...props }, ref) => {
    const alignClasses = {
      left: "justify-start",
      center: "justify-center",
      right: "justify-end",
      'space-between': "justify-between",
    };

    logger.debug('render', 'CardFooter rendering', { align });
    return (
      <div
        ref={ref}
        className={cn("flex items-center p-6 pt-0", alignClasses[align], className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CardFooter.displayName = 'CardFooter';
