"use client";

import { ReactNode, useCallback, useEffect, useRef, memo } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Dialog');

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  forceOpen?: boolean;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  showCloseButton?: boolean;
  closeOnOverlayClick?: boolean;
  closeOnEscape?: boolean;
  ariaLabel?: string;
  ariaDescribedBy?: string;
}

const sizeClasses = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-4xl',
  xl: 'max-w-6xl',
  full: 'max-w-[95vw]',
};

export const Dialog = memo(function Dialog({
  isOpen,
  onClose,
  title,
  children,
  forceOpen = false,
  size = 'lg',
  showCloseButton = true,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  ariaLabel,
  ariaDescribedBy,
}: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  const handleClose = useCallback(() => {
    if (!forceOpen) {
      logger.info('handleClose', 'Dialog closing');
      onClose();
    }
  }, [forceOpen, onClose]);

  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget && closeOnOverlayClick && !forceOpen) {
      handleClose();
    }
  }, [closeOnOverlayClick, forceOpen, handleClose]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape' && closeOnEscape && !forceOpen) {
        e.preventDefault();
        handleClose();
      }

      if (e.key === 'Tab') {
        const focusableElements = dialogRef.current?.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );

        if (focusableElements && focusableElements.length > 0) {
          const firstElement = focusableElements[0] as HTMLElement;
          const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

          if (e.shiftKey) {
            if (document.activeElement === firstElement) {
              e.preventDefault();
              lastElement.focus();
            }
          } else {
            if (document.activeElement === lastElement) {
              e.preventDefault();
              firstElement.focus();
            }
          }
        }
      }
    },
    [closeOnEscape, forceOpen, handleClose]
  );

  useEffect(() => {
    if (isOpen) {
      previousActiveElementRef.current = document.activeElement as HTMLElement;
      logger.info('useEffect', 'Dialog opened', { title, size });

      const timer = setTimeout(() => {
        dialogRef.current?.focus();
      }, 100);

      document.body.style.overflow = 'hidden';

      return () => {
        clearTimeout(timer);
        document.body.style.overflow = '';
        previousActiveElementRef.current?.focus();
        logger.info('useEffect', 'Dialog cleanup');
      };
    }
  }, [isOpen, title, size]);

  if (!isOpen) return null;

  const content = (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy}
    >
      <div
        className="fixed inset-0 z-[9999] bg-black/50 backdrop-blur-sm transition-opacity duration-300 animate-in fade-in"
        onClick={handleOverlayClick}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={cn(
          "relative z-[10000] bg-background rounded-xl shadow-2xl w-full mx-4 p-6",
          "transition-all duration-300 animate-in zoom-in-95 slide-in-from-bottom-4",
          sizeClasses[size]
        )}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-center justify-between mb-4">
          <h2
            id="dialog-title"
            className="text-xl font-bold text-foreground"
          >
            {title}
          </h2>
          {showCloseButton && !forceOpen && (
            <button
              onClick={handleClose}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 rounded-lg p-1"
              aria-label="关闭对话框"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
        <div className="max-h-[calc(100vh-8rem)] overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );

  return createPortal(content, document.body);
});
