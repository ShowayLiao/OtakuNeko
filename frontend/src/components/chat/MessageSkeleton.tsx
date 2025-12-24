"use client";

import React from 'react';

export const MessageSkeleton: React.FC = () => {
  return (
    <div className="flex items-end gap-4 mb-4">
      {/* Avatar skeleton */}
      <div className="w-12 h-12 rounded-2xl overflow-hidden bg-gray-200 animate-pulse"></div>

      {/* Message content skeleton */}
      <div className="flex flex-col max-w-[80%]">
        {/* Name skeleton */}
        <div className="h-3 w-20 bg-gray-200 rounded mb-2 animate-pulse"></div>

        {/* Bubble skeleton */}
        <div className="p-4 rounded-2xl bg-gray-200 rounded-bl-none animate-pulse">
          {/* Content skeleton */}
          <div className="space-y-2">
            <div className="h-3 w-40 bg-gray-300 rounded animate-pulse"></div>
            <div className="h-3 w-full bg-gray-300 rounded animate-pulse"></div>
            <div className="h-3 w-32 bg-gray-300 rounded animate-pulse"></div>
          </div>
        </div>

        {/* Timestamp skeleton */}
        <div className="h-2 w-16 bg-gray-200 rounded mt-2 animate-pulse"></div>
      </div>
    </div>
  );
};
