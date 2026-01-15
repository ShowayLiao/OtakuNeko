"use client";

import { type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface NavPillSkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string;
  count?: number;
}

const NavPillSkeleton = ({ width = "w-24", count = 1, ...props }: NavPillSkeletonProps) => {
  const skeletons = Array.from({ length: count }, (_, i) => (
    <div
      key={i}
      className={cn(
        "h-9 rounded-full bg-gradient-to-r from-gray-100 via-gray-50 to-gray-100",
        "dark:from-gray-800 dark:via-gray-750 dark:to-gray-800",
        "border border-gray-200 dark:border-gray-700",
        "relative overflow-hidden",
        "animate-pulse",
        "flex items-center justify-center",
        "transition-all duration-300",
        "hover:shadow-md",
        width
      )}
      {...props}
    >
      <div className="h-4 w-1/2 bg-foreground/20 dark:bg-foreground/10 rounded opacity-60" />
    </div>
  ));

  return <>{skeletons}</>;
};

export default NavPillSkeleton;