"use client";

import { useState, useCallback } from 'react';
import { Search, X, Loader2, Plus } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { searchSubjects } from '@/lib/api';
import type { Subject } from '@/lib/api';
import { CollectionAddForm } from './CollectionAddForm';

interface SubjectSearchFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function SubjectSearchForm({ isOpen, onClose, onSuccess }: SubjectSearchFormProps) {
  const { toast } = useToast();
  const [keyword, setKeyword] = useState('');
  const [results, setResults] = useState<Subject[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isAdding, setIsAdding] = useState<number | null>(null);
  const [isCollectionFormOpen, setIsCollectionFormOpen] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState<Subject | null>(null);

  // 处理搜索
  const handleSearch = useCallback(async () => {
    if (!keyword.trim()) {
      toast({
        type: 'info',
        message: '请输入搜索关键词'
      });
      return;
    }

    setIsSearching(true);
    try {
      const searchResults = await searchSubjects(keyword, 2, 'mixed', 20, 0, 'rank');
      setResults(searchResults);
      
      if (searchResults.length === 0) {
        toast({
          type: 'info',
          message: '没有找到匹配的条目'
        });
      }
    } catch (error) {
      console.error('Error searching subjects:', error);
      toast({
        type: 'error',
        message: '搜索失败，请稍后重试'
      });
    } finally {
      setIsSearching(false);
    }
  }, [keyword, toast]);

  // 处理添加收藏 - 打开表单
  const handleAddCollection = useCallback((subject: Subject) => {
    setSelectedSubject(subject);
    setIsCollectionFormOpen(true);
  }, []);

  // 处理收藏表单成功关闭
  const handleCollectionSuccess = useCallback(() => {
    onSuccess?.();
    // 不立即关闭搜索表单，让用户可以继续添加其他收藏
  }, [onSuccess]);

  // 处理键盘事件
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <>
      <Dialog isOpen={isOpen} onClose={onClose} title="添加收藏">
        <div className="space-y-4">
          {/* 搜索表单 */}
          <div className="flex gap-2">
            <Input
              type="text"
              placeholder="输入动画名称搜索..."
              value={keyword}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setKeyword(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSearching}
              className="flex-1"
            />
            <Button
              onClick={handleSearch}
              disabled={isSearching || !keyword.trim()}
            >
              {isSearching ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Search className="w-4 h-4" />
              )}
              搜索
            </Button>
          </div>

          {/* 搜索结果 */}
          <div className="max-h-96 overflow-y-auto">
            {isSearching ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
                <span className="ml-2">搜索中...</span>
              </div>
            ) : results.length > 0 ? (
              <div className="space-y-2">
                {results.map((subject, index) => (
                  <div key={subject.id || `remote-${index}-${subject.name}`} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-16 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0 relative">
                        {subject.cover_url && (
                          <img
                            src={subject.cover_url}
                            alt={subject.name}
                            className="w-full h-full object-cover rounded"
                            loading="lazy"
                          />
                        )}
                        {/* 收藏状态标识 */}
                        {subject.is_favorited && (
                          <div className="absolute top-1 right-1 bg-primary/80 text-white rounded-full p-1">
                            <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20" aria-hidden="true">
                              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                            </svg>
                          </div>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium truncate flex items-center gap-1">
                          {subject.name_cn || subject.name}
                          {/* 收藏状态文本标识 */}
                          {subject.is_favorited && (
                            <span className="text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 px-1.5 py-0.5 rounded">
                              已收藏
                            </span>
                          )}
                        </h4>
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                          {subject.name}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          {subject.score && (
                            <p className="text-xs text-yellow-600 dark:text-yellow-400 flex items-center gap-1">
                              <span className="inline-block w-3 h-3 text-yellow-500">★</span>
                              {subject.score}
                            </p>
                          )}
                          {subject.type && (
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              {subject.type === 2 ? '动画' : 
                               subject.type === 1 ? '书籍' : 
                               subject.type === 3 ? '音乐' : 
                               subject.type === 4 ? '游戏' : '三次元'}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleAddCollection(subject)}
                      disabled={subject.is_favorited}
                      variant={subject.is_favorited ? 'outline' : 'default'}
                    >
                      {subject.is_favorited ? (
                        '已添加'
                      ) : (
                        <>
                          <Plus className="w-4 h-4" />
                          添加
                        </>
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            ) : keyword ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                没有找到匹配的条目
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                请输入关键词搜索动画
              </div>
            )}
          </div>
        </div>
      </Dialog>
      
      {/* 收藏信息表单 */}
      <CollectionAddForm
        isOpen={isCollectionFormOpen}
        onClose={() => setIsCollectionFormOpen(false)}
        onSuccess={handleCollectionSuccess}
        subject={selectedSubject}
      />
    </>
  );
}
