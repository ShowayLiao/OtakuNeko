"use client";

const NavPillSkeleton = ({ width = "w-24" }) => (
  <div className={`h-9 ${width} rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 animate-pulse flex items-center justify-center`}>
    <div className="h-4 w-1/2 bg-gray-200 dark:bg-gray-700 rounded" />
  </div>
);

export default NavPillSkeleton;