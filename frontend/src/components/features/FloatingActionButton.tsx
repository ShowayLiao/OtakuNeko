"use client";

import { useState, useRef, useEffect, useCallback } from 'react';
import { Plus, PlusCircle, UploadCloud, Edit3, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToast } from '@/components/ui/Toast';
import { useHeaderContext } from '@/contexts/HeaderContext';

interface ActionItem {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  ariaLabel: string;
  type?: 'add' | 'import' | 'edit';
}

interface FloatingActionButtonProps {
  actions?: ActionItem[];
  className?: string;
  ariaLabel?: string;
  onActionSuccess?: (type: string, data?: any) => void;
}

export function FloatingActionButton({
  actions,
  className,
  ariaLabel = '操作菜单',
  onActionSuccess
}: FloatingActionButtonProps) {
  const { toast } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const fabRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // 从HeaderContext获取表单状态设置函数
  const { 
    setIsCollectionManagerOpen, 
    setIsDoubanImportOpen 
  } = useHeaderContext();

  // 默认操作配置
  const defaultActions: ActionItem[] = [
    {
      icon: <PlusCircle className="w-5 h-5" />,
      label: '添加/修改收藏',
      ariaLabel: '添加/修改收藏',
      type: 'add'
    },
    {
      icon: <UploadCloud className="w-5 h-5" />,
      label: '导入豆瓣收藏',
      ariaLabel: '导入豆瓣收藏',
      type: 'import'
    }
  ];

  // 使用传入的actions或默认actions
  const finalActions = actions || defaultActions;

  const handleClickOutside = useCallback((event: MouseEvent) => {
    if (fabRef.current && !fabRef.current.contains(event.target as Node)) {
      setIsOpen(false);
    }
  }, []);

  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [handleClickOutside]);

  const handleToggle = useCallback(() => {
    setIsOpen(prev => !prev);
  }, []);

  // 导入豆瓣收藏处理
  const handleImportDouban = useCallback(() => {
    setIsOpen(false);
    // 打开导入豆瓣收藏表单
    setIsDoubanImportOpen(true);
    onActionSuccess?.('import');
  }, [setIsDoubanImportOpen, onActionSuccess]);

  // 添加/修改收藏处理
  const handleAddEditCollection = useCallback(() => {
    setIsOpen(false);
    // 打开添加/修改收藏表单
    setIsCollectionManagerOpen(true);
    onActionSuccess?.('add-edit');
  }, [setIsCollectionManagerOpen, onActionSuccess]);

  // 处理文件选择 - 保留但移除不再使用的isLoading和activeAction状态
  const handleFileChange = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    try {
      // 这里可以添加文件处理逻辑，但根据新的设计，文件选择应该在表单内部处理
      toast({
        type: 'info',
        message: `选择了文件: ${file.name}`
      });
    } catch (error) {
      console.error('Error handling file:', error);
      toast({
        type: 'error',
        message: '处理文件失败，请稍后重试'
      });
    } finally {
      // 重置文件输入
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [toast]);

  // 处理操作项点击
  const handleActionClick = useCallback((action: ActionItem) => {
    setIsOpen(false);
    
    if (action.onClick) {
      action.onClick();
    } else if (action.type === 'add') {
      handleAddEditCollection();
    } else if (action.type === 'import') {
      handleImportDouban();
    }
  }, [handleAddEditCollection, handleImportDouban]);

  return (
    <div
      ref={fabRef}
      className={cn("fixed bottom-8 right-8 z-50 flex flex-col items-end gap-3", className)}
    >
      {/* 操作按钮 */}
      {finalActions.map((action, index) => (
        <button
          key={index}
          onClick={() => handleActionClick(action)}
          aria-label={action.ariaLabel}
          className={cn(
            "flex items-center gap-3 px-4 py-3 rounded-full",
            "bg-primary text-white shadow-lg",
            "hover:bg-primary/90",
            "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
            "focus:ring-offset-background dark:focus:ring-offset-gray-900",
            "transition-all duration-300 ease-out",
            "transform",
            isOpen
              ? "opacity-100 translate-y-0 scale-100"
              : "opacity-0 translate-y-4 scale-95 pointer-events-none"
          )}
          style={{
            transitionDelay: isOpen ? `${(finalActions.length - 1 - index) * 50}ms` : '0ms'
          }}
        >
          <span className="text-sm font-medium whitespace-nowrap">
            {action.label}
          </span>
          <span className="flex-shrink-0">
            {action.icon}
          </span>
        </button>
      ))}

      {/* 主按钮 */}
      <button
        onClick={handleToggle}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        className={cn(
          "w-14 h-14 rounded-full",
          "bg-primary text-white shadow-xl",
          "hover:bg-primary/90",
          "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
          "focus:ring-offset-background dark:focus:ring-offset-gray-900",
          "flex items-center justify-center",
          "transition-all duration-300 ease-out",
          "transform hover:scale-105 active:scale-95"
        )}
      >
        {isOpen ? (
          <X className="w-6 h-6 transition-transform duration-300 rotate-0" />
        ) : (
          <Plus className="w-6 h-6 transition-transform duration-300 rotate-0" />
        )}
      </button>
    </div>
  );
}
