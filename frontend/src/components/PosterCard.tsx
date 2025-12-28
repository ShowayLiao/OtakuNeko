"use client";

import { useState } from 'react';
import Image from 'next/image';
import { getImageProps } from '@/lib/image-config';

interface PosterCardProps {
  id: number;
  name_cn: string;
  cover_url: string;
  score: number;
  tags: string[];
  href: string;
  priority?: boolean;
  images?: {
    large: string;
    common: string;
    medium: string;
    small: string;
    grid: string;
  };
}

export function PosterCard({ id, name_cn, cover_url, score, tags, href, priority = false, images }: PosterCardProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [imageError, setImageError] = useState(false);
  
  const imageUrl = images?.common || images?.medium || cover_url;
  const imageProps = getImageProps(imageUrl);

  return (
    <a
      key={id}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative aspect-[2/3] rounded-lg overflow-hidden cursor-pointer bg-gray-200 dark:bg-gray-800"
    >
      {/* 海报图片容器 */}
      <div className="relative w-full h-full overflow-hidden">
        {/* 使用Next.js Image组件 */}
        {!imageError ? (
          <Image
              src={imageUrl}
              alt={name_cn}
              fill={true}
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, (max-width: 1280px) 25vw, 20vw"
              className={`
                object-cover duration-700 ease-in-out
                ${isLoading ? 'scale-110 blur-xl grayscale' : 'scale-100 blur-0 grayscale-0'}
                group-hover:scale-110 group-hover:brightness-50
              `}
              priority={priority}
              loading={priority ? undefined : 'lazy'}
              unoptimized={imageProps.unoptimized}
              referrerPolicy={imageProps.referrerPolicy}
              onLoadingComplete={() => setIsLoading(false)}
              onError={() => setImageError(true)}
            />
        ) : (
          <div className="flex items-center justify-center w-full h-full bg-gray-300 dark:bg-gray-700">
            <span className="text-gray-500 dark:text-gray-400">暂无图片</span>
          </div>
        )}
      </div>

      {/* 悬浮交互层 */}
      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-4">
        {/* 标题 */}
        <h3 className="text-white font-bold text-lg mb-2 line-clamp-2">{name_cn}</h3>
          
        {/* 评分 */}
        <div className="flex items-center mb-3">
          <span className="text-yellow-300 mr-1">⭐</span>
          <span className="text-white font-semibold">{score}</span>
        </div>
          
        {/* 标签 */}
        <div className="flex flex-wrap gap-2">
          {tags.slice(0, 3).map((tag, index) => (
            <span
              key={index}
              className="text-xs bg-white/20 px-2 py-1 rounded-full text-white"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </a>
  );
}