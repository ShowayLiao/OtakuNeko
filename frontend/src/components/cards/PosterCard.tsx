"use client";

import { useState, useCallback, useMemo, forwardRef, useEffect, useId, useRef } from 'react';
import Image from 'next/image';
import { getImageProps } from '@/lib/image-config';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('PosterCard');

export interface PosterImages {
  large: string;
  common: string;
  medium: string;
  small: string;
  grid: string;
}

export interface PosterCardProps {
  id: number;
  name_cn: string;
  cover_url: string;
  score: number;
  tags: string[];
  href: string;
  priority?: boolean;
  images?: PosterImages;
  className?: string;
  ariaLabel?: string;
  onImageLoad?: () => void;
  onImageError?: () => void;
  onClick?: (event: React.MouseEvent<HTMLAnchorElement>) => void;
  onKeyDown?: (event: React.KeyboardEvent<HTMLAnchorElement>) => void;
}

export const PosterCard = forwardRef<HTMLAnchorElement, PosterCardProps>(
  ({
    id,
    name_cn,
    cover_url,
    score,
    tags,
    href,
    priority = false,
    images,
    className,
    ariaLabel,
    onImageLoad,
    onImageError,
    onClick,
    onKeyDown,
  }, ref) => {
    const [isLoading, setIsLoading] = useState(true);
    const [imageError, setImageError] = useState(false);
    const [isFocused, setIsFocused] = useState(false);
    const [retryCount, setRetryCount] = useState(0);
    const [showRetryButton, setShowRetryButton] = useState(false);
    const cardId = useId();
    const imageRef = useRef<HTMLImageElement>(null);
    const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const imageUrl = useMemo(() => {
      return images?.common || images?.medium || cover_url;
    }, [images, cover_url]);

    const imageProps = useMemo(() => {
      return getImageProps(imageUrl);
    }, [imageUrl]);

    const displayedTags = useMemo(() => {
      return tags.slice(0, 3);
    }, [tags]);

    useEffect(() => {
      logger.debug('render', 'PosterCard rendering', { 
        id, 
        name_cn, 
        score, 
        tagsCount: tags.length,
        hasImages: !!images,
        priority,
        isLoading,
        imageError,
        isFocused,
        retryCount,
        showRetryButton
      });
      
      return () => {
        if (retryTimeoutRef.current) {
          clearTimeout(retryTimeoutRef.current);
        }
      };
    }, [id, name_cn, score, tags.length, images, priority, isLoading, imageError, isFocused, retryCount, showRetryButton]);

    const handleImageLoad = useCallback(() => {
      logger.debug('handleImageLoad', 'Poster image loaded', { id, name_cn, imageUrl });
      setIsLoading(false);
      setImageError(false);
      setShowRetryButton(false);
      onImageLoad?.();
    }, [id, name_cn, imageUrl, onImageLoad]);

    const handleImageError = useCallback(() => {
      logger.warn('handleImageError', 'Poster image failed to load', { id, name_cn, imageUrl, retryCount });
      
      if (retryCount < 2) {
        setRetryCount(prev => prev + 1);
        setShowRetryButton(true);
        
        if (retryTimeoutRef.current) {
          clearTimeout(retryTimeoutRef.current);
        }
        
        retryTimeoutRef.current = setTimeout(() => {
          setShowRetryButton(false);
          setImageError(true);
          setIsLoading(false);
          onImageError?.();
        }, 3000);
      } else {
        setImageError(true);
        setIsLoading(false);
        setShowRetryButton(false);
        onImageError?.();
      }
    }, [id, name_cn, imageUrl, retryCount, onImageError]);

    const handleRetry = useCallback((event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      logger.info('handleRetry', 'Retrying image load', { id, name_cn, imageUrl });
      setRetryCount(0);
      setShowRetryButton(false);
      setImageError(false);
      setIsLoading(true);
      
      if (imageRef.current) {
        imageRef.current.src = imageUrl + '?retry=' + Date.now();
      }
    }, [id, name_cn, imageUrl]);

    const handleClick = useCallback((event: React.MouseEvent<HTMLAnchorElement>) => {
      logger.info('handleClick', 'Poster card clicked', { id, name_cn, href });
      onClick?.(event);
    }, [id, name_cn, href, onClick]);

    const handleFocus = useCallback(() => {
      setIsFocused(true);
      logger.debug('handleFocus', 'Poster card focused', { id, name_cn });
    }, [id, name_cn]);

    const handleBlur = useCallback(() => {
      setIsFocused(false);
      logger.debug('handleBlur', 'Poster card blurred', { id, name_cn });
    }, [id, name_cn]);

    const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLAnchorElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        logger.info('handleKeyDown', 'Poster card activated via keyboard', { id, name_cn, key: event.key });
      }
      onKeyDown?.(event);
    }, [id, name_cn, onKeyDown]);

    const defaultAriaLabel = useMemo(() => {
      return `${name_cn}, 评分: ${score}, 标签: ${displayedTags.join(', ')}`;
    }, [name_cn, score, displayedTags]);

    return (
      <a
        ref={ref}
        id={cardId}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "group relative aspect-[2/3] rounded-lg overflow-hidden cursor-pointer bg-gray-100 dark:bg-gray-900",
          "focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2",
          "transition-all duration-300 ease-out",
          "hover:shadow-2xl hover:shadow-primary/20 hover:-translate-y-1",
          isFocused && "ring-2 ring-primary/50 ring-offset-2",
          className
        )}
        aria-label={ariaLabel || defaultAriaLabel}
        onClick={handleClick}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        role="article"
        tabIndex={0}
      >
        <div className="relative w-full h-full overflow-hidden">
          {!imageError ? (
            <Image
              ref={imageRef}
              src={imageUrl}
              alt={name_cn}
              fill={true}
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, (max-width: 1280px) 25vw, 20vw"
              className={cn(
                "object-cover duration-700 ease-in-out",
                isLoading ? 'scale-110 blur-xl grayscale' : 'scale-100 blur-0 grayscale-0',
                "group-hover:scale-110 group-hover:brightness-50 group-hover:blur-sm",
                "transition-all duration-500 ease-out"
              )}
              priority={priority}
              loading={priority ? undefined : 'lazy'}
              unoptimized={imageProps.unoptimized}
              referrerPolicy={imageProps.referrerPolicy}
              onLoadingComplete={handleImageLoad}
              onError={handleImageError}
            />
          ) : (
            <div 
              className="flex flex-col items-center justify-center w-full h-full bg-gradient-to-br from-gray-300 to-gray-400 dark:from-gray-700 dark:to-gray-800"
              role="img"
              aria-label={`${name_cn} - 图片加载失败`}
            >
              <svg 
                className="w-12 h-12 mb-2 text-gray-400 dark:text-gray-500"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={2} 
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" 
                />
              </svg>
              <span className="text-sm text-gray-600 dark:text-gray-400 mb-3">暂无图片</span>
              <button
                onClick={handleRetry}
                className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2 transition-colors"
                aria-label={`重新加载 ${name_cn} 的图片`}
              >
                重试
              </button>
            </div>
          )}
        </div>

        <div 
          className={cn(
            "absolute inset-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent flex flex-col justify-end p-4",
            "transition-opacity duration-300 ease-out",
            "opacity-0 group-hover:opacity-100",
            isFocused && "opacity-100",
            "backdrop-blur-[2px]"
          )}
          aria-hidden="true"
        >
          <h3 className="text-foreground font-bold text-lg mb-2 line-clamp-2 transition-all duration-300 ease-out group-hover:translate-y-0 translate-y-4">
            {name_cn}
          </h3>
          
          <div className="flex items-center mb-3 transition-all duration-300 ease-out group-hover:translate-y-0 translate-y-4">
            <span className="text-yellow-300 mr-1" aria-hidden="true">⭐</span>
            <span className="text-foreground font-semibold">{score}</span>
          </div>
          
          <div className="flex flex-wrap gap-2 transition-all duration-300 ease-out group-hover:translate-y-0 translate-y-4">
            {displayedTags.map((tag, index) => (
              <Badge
                key={`${tag}-${index}`}
                variant="outline"
                className="bg-white/20 text-white border-white/30 backdrop-blur-sm hover:bg-white/30 transition-colors"
                showDot={false}
                aria-label={`标签: ${tag}`}
              >
                {tag}
              </Badge>
            ))}
            {tags.length > 3 && (
              <Badge
                variant="outline"
                className="bg-white/20 text-white border-white/30 backdrop-blur-sm hover:bg-white/30 transition-colors"
                showDot={false}
                aria-label={`还有 ${tags.length - 3} 个标签`}
              >
                +{tags.length - 3}
              </Badge>
            )}
          </div>
        </div>

        {isLoading && !imageError && (
          <div 
            className="absolute inset-0 flex items-center justify-center bg-gray-200 dark:bg-gray-800"
            aria-hidden="true"
          >
            <div className="relative w-full h-full overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-gray-300 to-gray-400 dark:from-gray-700 dark:to-gray-800 animate-pulse" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-8 h-8 border-4 border-gray-400 border-t-primary rounded-full animate-spin" />
              </div>
            </div>
          </div>
        )}
      </a>
    );
  }
);

PosterCard.displayName = 'PosterCard';