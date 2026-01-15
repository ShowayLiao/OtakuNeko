"use client";

import { createContext, useContext, useState, useCallback, useRef, useEffect, useMemo, ReactNode, forwardRef } from 'react';
import { CheckCircle, XCircle, AlertCircle, Info, X, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { createComponentLogger } from '@/lib/logger';

const logger = createComponentLogger('Toast');

export type ToastType = 'success' | 'error' | 'info' | 'warning' | 'loading';

export type ToastPosition = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center' | 'bottom-center';

export interface ToastAction {
  label: string;
  onClick: () => void;
  variant?: 'default' | 'destructive';
}

export interface Toast {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
  action?: ToastAction;
  showProgress?: boolean;
  progress?: number;
}

export interface ToastContextType {
  toast: (props: Omit<Toast, 'id'>) => void;
  success: (message: string, title?: string, duration?: number) => void;
  error: (message: string, title?: string, duration?: number) => void;
  info: (message: string, title?: string, duration?: number) => void;
  warning: (message: string, title?: string, duration?: number) => void;
  loading: (message: string, title?: string) => void;
  dismiss: (id: string) => void;
  dismissAll: () => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

export interface ToastProviderProps {
  children: ReactNode;
  position?: ToastPosition;
  maxToasts?: number;
  defaultDuration?: number;
}

export function ToastProvider({ 
  children, 
  position = 'top-right',
  maxToasts = 5,
  defaultDuration = 3000
}: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timeoutsRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  const dismiss = useCallback((id: string) => {
    logger.debug('dismiss', 'Toast dismissed', { id });
    const timeout = timeoutsRef.current.get(id);
    if (timeout) {
      clearTimeout(timeout);
      timeoutsRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const dismissAll = useCallback(() => {
    logger.info('dismissAll', 'All toasts dismissed', { count: toasts.length });
    timeoutsRef.current.forEach((timeout) => clearTimeout(timeout));
    timeoutsRef.current.clear();
    setToasts([]);
  }, [toasts.length]);

  const toast = useCallback(({ type, title, message, duration, action, showProgress, progress }: Omit<Toast, 'id'>) => {
    const id = Math.random().toString(36).substr(2, 9);
    const actualDuration = duration ?? defaultDuration;
    
    logger.info('toast', 'Toast created', { id, type, title, message, duration: actualDuration });
    
    setToasts((prev) => {
      const newToasts = [...prev, { id, type, title, message, duration: actualDuration, action, showProgress, progress }];
      return newToasts.slice(-maxToasts);
    });

    if (actualDuration > 0 && type !== 'loading') {
      const timeout = setTimeout(() => {
        dismiss(id);
      }, actualDuration);
      timeoutsRef.current.set(id, timeout);
    }
  }, [dismiss, defaultDuration, maxToasts]);

  const success = useCallback((message: string, title?: string, duration?: number) => {
    toast({ type: 'success', title, message, duration });
  }, [toast]);

  const error = useCallback((message: string, title?: string, duration?: number) => {
    toast({ type: 'error', title, message, duration });
  }, [toast]);

  const info = useCallback((message: string, title?: string, duration?: number) => {
    toast({ type: 'info', title, message, duration });
  }, [toast]);

  const warning = useCallback((message: string, title?: string, duration?: number) => {
    toast({ type: 'warning', title, message, duration });
  }, [toast]);

  const loading = useCallback((message: string, title?: string) => {
    toast({ type: 'loading', title, message, duration: 0 });
  }, [toast]);

  useEffect(() => {
    const timeouts = timeoutsRef.current;
    return () => {
      timeouts.forEach((timeout) => clearTimeout(timeout));
    };
  }, []);

  const contextValue = useMemo(() => ({
    toast,
    success,
    error,
    info,
    warning,
    loading,
    dismiss,
    dismissAll
  }), [toast, success, error, info, warning, loading, dismiss, dismissAll]);

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} position={position} />
    </ToastContext.Provider>
  );
}

interface ToasterProps {
  toasts: Toast[];
  onDismiss: (id: string) => void;
  position: ToastPosition;
}

function Toaster({ toasts, onDismiss, position }: ToasterProps) {
  if (toasts.length === 0) return null;

  const positionClasses = {
    'top-left': 'top-4 left-4',
    'top-right': 'top-4 right-4',
    'bottom-left': 'bottom-4 left-4',
    'bottom-right': 'bottom-4 right-4',
    'top-center': 'top-4 left-1/2 -translate-x-1/2',
    'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2'
  };

  const directionClasses = {
    'top-left': 'flex-col',
    'top-right': 'flex-col',
    'bottom-left': 'flex-col-reverse',
    'bottom-right': 'flex-col-reverse',
    'top-center': 'flex-col',
    'bottom-center': 'flex-col-reverse'
  };

  return (
    <div 
      className={cn(
        "fixed z-50 flex gap-2 pointer-events-none",
        positionClasses[position],
        directionClasses[position]
      )}
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

const ToastItem = forwardRef<HTMLDivElement, ToastItemProps>(({ toast, onDismiss }, ref) => {
  const [progress, setProgress] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const progressRef = useRef<number>(0);
  const animationFrameRef = useRef<number | undefined>(undefined);

  const icons = useMemo(() => ({
    success: <CheckCircle className="w-5 h-5 text-green-500" aria-hidden="true" />,
    error: <XCircle className="w-5 h-5 text-red-500" aria-hidden="true" />,
    info: <Info className="w-5 h-5 text-blue-500" aria-hidden="true" />,
    warning: <AlertCircle className="w-5 h-5 text-yellow-500" aria-hidden="true" />,
    loading: <Loader2 className="w-5 h-5 text-blue-500 animate-spin" aria-hidden="true" />
  }), []);

  const bgColors = useMemo(() => ({
    success: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
    error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
    info: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    warning: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
    loading: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
  }), []);

  useEffect(() => {
    logger.debug('render', 'ToastItem rendering', { id: toast.id, type: toast.type });
  }, [toast.id, toast.type]);

  useEffect(() => {
    if (toast.duration && toast.duration > 0 && toast.type !== 'loading' && !isHovered) {
      const startTime = Date.now();
      const duration = toast.duration;

      const animate = () => {
        const elapsed = Date.now() - startTime;
        const newProgress = Math.min((elapsed / duration) * 100, 100);
        progressRef.current = newProgress;
        setProgress(newProgress);

        if (newProgress < 100) {
          animationFrameRef.current = requestAnimationFrame(animate);
        }
      };

      animationFrameRef.current = requestAnimationFrame(animate);

      return () => {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
      };
    }
  }, [toast.duration, toast.type, isHovered]);

  const handleDismiss = useCallback(() => {
    logger.debug('handleDismiss', 'Toast dismiss button clicked', { id: toast.id });
    onDismiss(toast.id);
  }, [toast.id, onDismiss]);

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
    if (toast.duration && toast.duration > 0 && toast.type !== 'loading') {
      const duration = toast.duration;
      const elapsed = (progressRef.current / 100) * duration;
      const remainingDuration = duration - elapsed;

      if (remainingDuration > 0) {
        setTimeout(() => {
          onDismiss(toast.id);
        }, remainingDuration);
      }
    }
  }, [toast.duration, toast.type, toast.id, onDismiss]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === 'Escape' || event.key === 'Enter') {
      event.preventDefault();
      handleDismiss();
    }
  }, [handleDismiss]);

  const handleAction = useCallback(() => {
    logger.info('handleAction', 'Toast action clicked', { id: toast.id, action: toast.action?.label });
    toast.action?.onClick();
    handleDismiss();
  }, [toast.id, toast.action, handleDismiss]);

  return (
    <div
      ref={ref}
      role="alert"
      aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
      className={cn(
        "pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-lg border shadow-lg",
        "animate-in slide-in-from-right-full fade-in duration-300",
        "hover:shadow-xl transition-shadow",
        bgColors[toast.type]
      )}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <div className="flex-shrink-0 mt-0.5">
        {icons[toast.type]}
      </div>
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className="text-sm font-semibold text-foreground mb-1">
            {toast.title}
          </p>
        )}
        <p className="text-sm text-foreground">
          {toast.message}
        </p>
        {toast.action && (
          <button
            onClick={handleAction}
            className={cn(
              "mt-2 text-sm font-medium underline focus:outline-none focus:ring-2 focus:ring-primary/50 rounded",
              toast.action.variant === 'destructive'
                ? "text-red-600 dark:text-red-400 hover:text-red-700"
                : "text-primary hover:text-primary/80"
            )}
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <button
        onClick={handleDismiss}
        className="flex-shrink-0 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/50 rounded p-1"
        aria-label="Dismiss notification"
      >
        <X className="w-4 h-4" />
      </button>
      {toast.showProgress && toast.duration && toast.duration > 0 && toast.type !== 'loading' && (
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-200 dark:bg-gray-700 rounded-b-lg overflow-hidden">
          <div
            className="h-full bg-current transition-all duration-100 ease-linear"
            style={{
              width: `${progress}%`,
              opacity: isHovered ? 0.3 : 1
            }}
            aria-hidden="true"
          />
        </div>
      )}
    </div>
  );
});

ToastItem.displayName = 'ToastItem';
