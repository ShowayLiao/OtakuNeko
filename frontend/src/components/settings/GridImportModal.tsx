"use client";

import { useState, useCallback, useEffect } from 'react';
import Image from 'next/image';
import { Search, X, Plus, Trash2, Check, Loader2, Star, XCircle, ImageOff, Film } from 'lucide-react';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { searchSubjects, batchImportCollections, GridState, GridSlot, Subject, ImportItem, gridStateToImportItems } from '@/lib/api';
import { useToast } from '../ui/Toast';
import { useSettings } from '@/contexts/SettingsContext';

interface GridImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

const CATEGORIES = [
  '动作/热血',
  '科幻',
  '奇幻/异世界',
  '喜剧',
  '悬疑/恐怖',
  '校园/日常',
  '音乐/偶像',
  '运动',
  '美食',
  '百合/萌系',
  '耽美',
  '爱情'
];

const initialGridState: GridState = CATEGORIES.reduce((acc, category) => {
  acc[category] = {
    best: { subject: null, type: 'best' },
    worst: { subject: null, type: 'worst' }
  };
  return acc;
}, {} as GridState);

export function GridImportModal({ isOpen, onClose, onSuccess }: GridImportModalProps) {
  const { toast } = useToast();
  const { settings } = useSettings();
  
  const [gridState, setGridState] = useState<GridState>(initialGridState);
  const [searchResults, setSearchResults] = useState<Subject[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [activeSlot, setActiveSlot] = useState<{ category: string; type: 'best' | 'worst' } | null>(null);
  const [searchKeyword, setSearchKeyword] = useState('');

  // 重置导入进度
  useEffect(() => {
    if (!isOpen) {
      setImportProgress(0);
    }
  }, [isOpen]);

  const resetState = useCallback(() => {
    setGridState(initialGridState);
    setSearchResults([]);
    setIsSearching(false);
    setIsImporting(false);
    setImportProgress(0);
    setActiveSlot(null);
    setSearchKeyword('');
  }, []);

  const handleSearch = useCallback(async (keyword: string) => {
    if (!keyword.trim()) {
      setSearchResults([]);
      return;
    }

    setIsSearching(true);
    try {
      // 使用新的searchSubjects方法
      const results = await searchSubjects(keyword, 2);
      setSearchResults(results);
    } catch (error) {
      console.error('Error searching subjects:', error);
      toast({
        type: 'error',
        message: '搜索失败，请稍后重试'
      });
    } finally {
      setIsSearching(false);
    }
  }, [toast]);

  const handleSelectSubject = useCallback((subject: Subject) => {
    if (!activeSlot) return;

    setGridState(prev => ({
      ...prev,
      [activeSlot.category]: {
        ...prev[activeSlot.category],
        [activeSlot.type]: { subject, type: activeSlot.type }
      }
    }));

    setActiveSlot(null);
    setSearchKeyword('');
    setSearchResults([]);
  }, [activeSlot]);

  const handleClearSlot = useCallback((category: string, type: 'best' | 'worst') => {
    setGridState(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [type]: { subject: null, type }
      }
    }));
  }, []);

  const handleClearAll = useCallback(() => {
    setGridState(initialGridState);
  }, []);

  const handleImport = useCallback(async () => {
    // 使用辅助函数将gridState转换为ImportItem数组
    const items = gridStateToImportItems(gridState);

    if (items.length === 0) {
      toast({
        type: 'error',
        message: '请至少选择一个动画'
      });
      return;
    }

    setIsImporting(true);
    try {
      // 使用新的batchImportCollections方法，不需要用户名参数
      const result = await batchImportCollections(items);
      toast({
        type: 'success',
        message: `成功导入 ${result.sync_count} 条数据`
      });
      onClose();
      onSuccess?.();
    } catch (error) {
      console.error('Error importing grid data:', error);
      let errorMessage = '导入失败，请稍后重试';
      
      // 提取更详细的错误信息
      if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === 'object' && error !== null) {
        if ('response' in error && typeof error.response === 'object' && error.response !== null) {
          const response = error.response as any;
          if (response.data && response.data.detail) {
            errorMessage = response.data.detail;
          } else if (response.status) {
            errorMessage = `HTTP错误: ${response.status} ${response.statusText || ''}`;
          }
        }
      }
      
      toast({
        type: 'error',
        message: errorMessage
      });
    } finally {
      setIsImporting(false);
    }
  }, [gridState, toast, onClose, onSuccess]);

  const getFilledCount = useCallback(() => {
    let count = 0;
    for (const category of CATEGORIES) {
      if (gridState[category].best.subject) count++;
      if (gridState[category].worst.subject) count++;
    }
    return count;
  }, [gridState]);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [resetState, onClose]);

  if (!isOpen) return null;

  return (
    <Dialog isOpen={isOpen} onClose={handleClose} title="填写动画喜好宫格">
      <div className="space-y-6">
        <div className="text-sm text-gray-600 dark:text-gray-400">
          在每个分类中选择你最喜欢的和最不喜欢的动画，系统将根据你的喜好生成个性化推荐。
          <br />
          已填写: <span className="font-semibold text-primary">{getFilledCount()}</span> / 24 个格子
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-[60vh] overflow-y-auto pr-2">
          {CATEGORIES.map((category) => {
            const categoryData = gridState[category];
            const bestSlot = categoryData.best;
            const worstSlot = categoryData.worst;

            return (
              <div key={category} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 space-y-3">
                <h3 className="font-semibold text-gray-900 dark:text-white text-center">{category}</h3>
                
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Star className="w-4 h-4 text-yellow-500 flex-shrink-0" />
                    <span className="text-xs text-gray-600 dark:text-gray-400 flex-shrink-0">最佳</span>
                  </div>
                  <SlotCard
                    slot={bestSlot}
                    onSelect={() => setActiveSlot({ category, type: 'best' })}
                    onClear={() => handleClearSlot(category, 'best')}
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                    <span className="text-xs text-gray-600 dark:text-gray-400 flex-shrink-0">最差</span>
                  </div>
                  <SlotCard
                    slot={worstSlot}
                    onSelect={() => setActiveSlot({ category, type: 'worst' })}
                    onClear={() => handleClearSlot(category, 'worst')}
                  />
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button
            variant="outline"
            onClick={handleClearAll}
            disabled={getFilledCount() === 0}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            清空
          </Button>
          <Button
            variant="outline"
            onClick={handleClose}
          >
            取消
          </Button>
          <Button
            onClick={handleImport}
            disabled={getFilledCount() === 0 || isImporting}
          >
            {isImporting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                导入中...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                一键导入
              </>
            )}
          </Button>
        </div>
      </div>

      {activeSlot && (
        <SubjectSearchDialog
          isOpen={true}
          onClose={() => {
            setActiveSlot(null);
            setSearchKeyword('');
            setSearchResults([]);
          }}
          onSearch={handleSearch}
          onSelect={handleSelectSubject}
          results={searchResults}
          isSearching={isSearching}
          keyword={searchKeyword}
          onKeywordChange={setSearchKeyword}
        />
      )}
    </Dialog>
  );
}

interface SlotCardProps {
  slot: GridSlot;
  onSelect: () => void;
  onClear: () => void;
}

function SlotCard({ slot, onSelect, onClear }: SlotCardProps) {
  if (slot.subject) {
    return (
      <div className="relative group">
        <div className="bg-white dark:bg-gray-800 rounded-lg p-2 shadow-sm border border-gray-200 dark:border-gray-600">
          <div className="flex items-center gap-3">
            {slot.subject.cover_url ? (
              <div className="relative w-12 h-16 flex-shrink-0">
                <Image
                  src={slot.subject.cover_url}
                  alt={slot.subject.name}
                  fill
                  className="object-cover rounded"
                  unoptimized
                />
              </div>
            ) : (
              <div className="w-12 h-16 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0 flex items-center justify-center">
                <Film className="w-5 h-5 text-gray-400" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {slot.subject.name_cn || slot.subject.name}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {slot.subject.name}
              </p>
            </div>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClear();
          }}
          className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={onSelect}
      className="w-full h-20 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg flex items-center justify-center hover:border-primary dark:hover:border-primary transition-colors group"
    >
      <Plus className="w-6 h-6 text-gray-400 group-hover:text-primary transition-colors" />
    </button>
  );
}

interface SubjectSearchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSearch: (keyword: string) => void;
  onSelect: (subject: Subject) => void;
  results: Subject[];
  isSearching: boolean;
  keyword: string;
  onKeywordChange: (keyword: string) => void;
}

function SubjectSearchDialog({
  isOpen,
  onClose,
  onSearch,
  onSelect,
  results,
  isSearching,
  keyword,
  onKeywordChange
}: SubjectSearchDialogProps) {
  if (!isOpen) return null;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      onSearch(keyword);
    }
  };

  const handleSearchClick = () => {
    onSearch(keyword);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-2xl mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">搜索动画</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mb-4">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                type="text"
                placeholder="输入动画名称搜索..."
                value={keyword}
                onChange={(e) => onKeywordChange(e.target.value)}
                onKeyDown={handleKeyDown}
                className="pl-10"
                autoFocus
              />
            </div>
            <Button
              onClick={handleSearchClick}
              disabled={isSearching || !keyword.trim()}
            >
              {isSearching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            按 Enter 键或点击搜索按钮进行搜索
          </p>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {isSearching ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
            </div>
          ) : results.length > 0 ? (
            <div className="space-y-2">
              {results.map((subject, index) => (
                <button
                  key={subject.id ? String(subject.id) : `subject-${index}-${subject.name}`}
                  onClick={() => onSelect(subject)}
                  className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-left"
                >
                  {subject.cover_url ? (
                    <div className="relative w-12 h-16 flex-shrink-0">
                      <Image
                        src={subject.cover_url}
                        alt={subject.name}
                        fill
                        className="object-cover rounded"
                        unoptimized
                      />
                    </div>
                  ) : (
                    <div className="w-12 h-16 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0 flex items-center justify-center">
                      <ImageOff className="w-5 h-5 text-gray-400" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {subject.name_cn || subject.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {subject.name}
                    </p>
                    {subject.score && (
                      <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                        评分: {subject.score}
                      </p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          ) : keyword ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              未找到相关动画
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              请输入关键词搜索动画
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
