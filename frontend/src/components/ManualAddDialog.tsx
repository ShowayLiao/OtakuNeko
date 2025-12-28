"use client";

import { useState, useCallback, useEffect, useRef } from 'react';
import { Loader2, Image as ImageIcon, UploadCloud, Search, X, BookMarked, Globe } from 'lucide-react';
import { Dialog } from './ui/Dialog';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/Tabs';
import { useToast } from './ui/Toast';
import { useManualAddDialogStore } from '@/lib/manualAddDialogStore';
import api, { searchMixedSubjects, Subject, createManualCollection } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';

interface ManualAddDialogProps {
  isOpen?: boolean;
  onClose?: () => void;
  onSuccess: () => void;
}

export function ManualAddDialog({ isOpen: propsIsOpen, onClose: propsOnClose, onSuccess }: ManualAddDialogProps) {
  const { isOpen: storeIsOpen, selectedSubject, closeDialog } = useManualAddDialogStore();
  const { settings } = useSettings();
  
  // Use store state if available, otherwise use props
  const isOpen = storeIsOpen ?? propsIsOpen ?? false;
  const onClose = storeIsOpen ? closeDialog : propsOnClose;
  
  const nameInputRef = useRef<HTMLInputElement>(null);
  
  // 收藏状态字符串到数字的映射
  const statusStringToNumber = useCallback((statusStr: string | undefined): number => {
    const statusMap: Record<string, number> = {
      'wish': 1,
      'collect': 2,
      'do': 3,
      'on_hold': 4,
      'dropped': 5
    };
    return statusMap[statusStr || ''] ?? 1;
  }, []);
  
  const [name, setName] = useState('');
  const [coverUrl, setCoverUrl] = useState('');
  const [type, setType] = useState<number>(2);
  const [status, setStatus] = useState<number>(1);
  const [rate, setRate] = useState<number>(0);
  const [comment, setComment] = useState('');
  const [date, setDate] = useState('');
  const [tags, setTags] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [imageError, setImageError] = useState(false);
  const { toast } = useToast();

  const [searchResults, setSearchResults] = useState<Subject[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [existingSubjectId, setExistingSubjectId] = useState<number | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [searchMode, setSearchMode] = useState<'library' | 'global'>('library');

  const typeOptions = [
    { label: '书籍', value: 1 },
    { label: '动画', value: 2 },
    { label: '音乐', value: 3 },
    { label: '游戏', value: 4 },
    { label: '三次元', value: 6 }
  ];

  const statusOptions = [
    { label: '想看', value: 1 },
    { label: '看过', value: 2 },
    { label: '在看', value: 3 },
    { label: '搁置', value: 4 },
    { label: '抛弃', value: 5 }
  ];

  const handleImageLoad = useCallback(() => {
    setImageError(false);
  }, []);

  const handleImageError = useCallback(() => {
    setImageError(true);
  }, []);

  // Handle selectedSubject from store (when opened from Header search)
  useEffect(() => {
    if (selectedSubject && storeIsOpen) {
      handleSelectSubject(selectedSubject);
    }
  }, [selectedSubject, storeIsOpen]);

  const handleSearch = async () => {
    if (name.length < 2) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }

    setIsSearching(true);
    try {
      const results = await searchMixedSubjects(name, type, settings.username);
      
      if (searchMode === 'library') {
        setSearchResults(results.filter(r => r.is_collected));
      } else {
        setSearchResults(results);
      }
      setShowSearchResults(results.length > 0);
    } catch (error) {
      console.error('Search error:', error);
      setSearchResults([]);
      setShowSearchResults(false);
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleSelectSubject = (subject: Subject) => {
    setShowSearchResults(false);

    setName(subject.name);
    setCoverUrl(subject.cover_url || '');
    setType(subject.type);
    setDate(subject.date || '');

    setExistingSubjectId(subject.id);

    if (subject.is_collected && subject.collection_info) {
      // === 场景 A: 已收藏 -> 进入编辑模式 ===
      console.log("命中已收藏条目:", subject.collection_info);

      setRate(subject.collection_info.rate || 0);
      setComment(subject.collection_info.comment || '');
      setTags(Array.isArray(subject.collection_info.tags) ? subject.collection_info.tags.join(', ') : '');
      setStatus(statusStringToNumber(subject.collection_info.status));

      setIsEditMode(true);
    } else {
      // === 场景 B: 未收藏 -> 进入新增模式 ===
      console.log("条目未收藏，准备新建收藏");

      setRate(0);
      setComment('');
      setTags('');
      setStatus(1);

      setIsEditMode(false);
    }
  };

  const handleClearSelection = () => {
    setSelectedSubjectId(null);
    setExistingSubjectId(null);
    setIsEditMode(false);
    setName('');
    setCoverUrl('');
    setType(2);
    setStatus(1);
    setRate(0);
    setComment('');
    setTags('');
    setDate('');
    setSearchResults([]);
    setShowSearchResults(false);
    
    setTimeout(() => {
      nameInputRef.current?.focus();
    }, 0);
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast({
        type: 'error',
        message: '请输入条目标题'
      });
      return;
    }

    if (!settings.username) {
      toast({
        type: 'error',
        message: '请先设置用户名'
      });
      return;
    }

    setIsSubmitting(true);

    try {
      const username = settings.username;
      
      const getTagsArray = (val: string | string[]) => {
        if (Array.isArray(val)) return val;
        return (val || "").split(/[,，]/).map(t => t.trim()).filter(Boolean);
      };

      const getTagsString = (val: string | string[]) => {
        if (Array.isArray(val)) return val.join(',');
        return val || "";
      };
      
      if (existingSubjectId && isEditMode) {
        const updatePayload = {
          status: Number(status),
          rate: Number(rate || 0),
          comment: comment || "",
          private: false,
          tags: getTagsArray(tags)
        };

        const response = await fetch(`http://localhost:8000/api/v1/collections/${existingSubjectId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(updatePayload)
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || '更新失败');
        }

        toast({
          type: 'success',
          message: '更新成功！'
        });
      } else {
        const createPayload = {
          name: name.trim(),
          type: Number(type),
          status: Number(status),
          cover_url: coverUrl.trim(),
          rate: Number(rate || 0),
          comment: comment || "",
          release_date: date || "",
          publish_date: date || "",
          tags: getTagsString(tags)
        };

        if (existingSubjectId) {
          await createManualCollection({
            subject_id: existingSubjectId,
            ...createPayload
          }, username);
        } else {
          await createManualCollection(createPayload, username);
        }

        toast({
          type: 'success',
          message: '添加成功！'
        });
      }

      setTimeout(() => {
        if (onClose) {
          onClose();
        }
        onSuccess();
      }, 1000);

    } catch (err) {
      console.error('操作失败:', err);
      const errorMessage = err instanceof Error ? err.message : '操作失败，请重试';
      toast({
        type: 'error',
        message: errorMessage
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = useCallback(() => {
    setName('');
    setCoverUrl('');
    setType(2);
    setStatus(1);
    setRate(0);
    setComment('');
    setDate('');
    setTags('');
    setImageError(false);
    setSearchResults([]);
    setIsSearching(false);
    setSelectedSubjectId(null);
    setShowSearchResults(false);
  }, []);

  const handleClose = useCallback(() => {
    resetForm();
    if (onClose) {
      onClose();
    }
  }, [resetForm, onClose]);

  return (
    <Dialog isOpen={isOpen} onClose={handleClose} title="条目信息">
      <div className="grid gap-8 py-6 md:grid-cols-[260px_1fr]">
        <div 
          className="relative w-full overflow-hidden rounded-lg border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800 self-start shadow-md" 
          style={{ aspectRatio: '2/3' }} 
        >
          {coverUrl ? (
            <>
              <img 
                src={coverUrl} 
                alt="Blur Background" 
                className="absolute inset-0 h-full w-full object-cover blur-xl opacity-40 scale-110" 
                referrerPolicy="no-referrer" 
              />
              <img 
                src={coverUrl} 
                alt="Cover" 
                className="relative h-full w-full object-contain z-10" 
                referrerPolicy="no-referrer" 
                onLoad={handleImageLoad}
                onError={handleImageError}
              />
            </>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-gray-500">
              <UploadCloud className="mb-3 h-12 w-12 opacity-20" />
              <span className="text-sm font-medium opacity-60">粘贴链接预览</span>
              <span className="text-xs opacity-40 mt-1">比例 2:3</span>
            </div>
          )}
        </div>

        <div className="grid gap-5">
          {selectedSubjectId || existingSubjectId ? (
            <div className="relative">
              <div className="flex items-center gap-4 p-4 rounded-lg border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                {coverUrl ? (
                  <img
                    src={coverUrl}
                    alt={name}
                    className="h-16 w-12 object-cover rounded shadow-sm"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="h-16 w-12 rounded bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                    <ImageIcon className="h-6 w-6 text-gray-400" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                    {name}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {typeOptions.find(opt => opt.value === type)?.label}
                  </div>
                </div>
                <button
                  onClick={handleClearSelection}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                  title="更换条目"
                >
                  <X className="w-3.5 h-3.5" />
                  更换
                </button>
              </div>
            </div>
          ) : (
            <div className="relative">
              <Tabs>
                <TabsList>
                  <TabsTrigger
                    value="library"
                    selectedValue={searchMode}
                    onClick={() => setSearchMode('library')}
                  >
                    <BookMarked className="w-4 h-4 mr-1.5" />
                    库内搜索
                  </TabsTrigger>
                  <TabsTrigger
                    value="global"
                    selectedValue={searchMode}
                    onClick={() => setSearchMode('global')}
                  >
                    <Globe className="w-4 h-4 mr-1.5" />
                    全站搜索
                  </TabsTrigger>
                </TabsList>
                
                <TabsContent value="library" selectedValue={searchMode}>
                  <div className="flex gap-2 mt-4">
                    <div className="relative flex-1">
                      <Input
                        label="标题"
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="搜索已收藏的条目"
                        disabled={isSubmitting}
                        required
                        autoFocus
                        ref={nameInputRef}
                        onKeyDown={handleKeyDown}
                      />
                    </div>
                    <Button
                      onClick={handleSearch}
                      disabled={isSearching || name.length < 2}
                      className="mt-[22px]"
                    >
                      {isSearching ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Search className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    仅显示已收藏的条目
                  </p>
                </TabsContent>
                
                <TabsContent value="global" selectedValue={searchMode}>
                  <div className="flex gap-2 mt-4">
                    <div className="relative flex-1">
                      <Input
                        label="标题"
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="搜索所有条目"
                        disabled={isSubmitting}
                        required
                        autoFocus
                        ref={nameInputRef}
                        onKeyDown={handleKeyDown}
                      />
                    </div>
                    <Button
                      onClick={handleSearch}
                      disabled={isSearching || name.length < 2}
                      className="mt-[22px]"
                    >
                      {isSearching ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Search className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    显示所有可用条目，包括未收藏的
                  </p>
                </TabsContent>
              </Tabs>
              
              {showSearchResults && searchResults.length > 0 && (
                <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800 max-h-64 overflow-y-auto">
                  {searchResults.map((subject, index) => (
                    <button
                      key={subject.id ? String(subject.id) : `subject-${index}`}
                      onClick={() => handleSelectSubject(subject)}
                      className="flex w-full items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-0"
                    >
                      {subject.cover_url && (
                        <img
                          src={subject.cover_url}
                          alt={subject.name}
                          className="h-12 w-8 object-cover rounded"
                          referrerPolicy="no-referrer"
                        />
                      )}
                      <div className="flex-1 text-left">
                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                          {subject.name}
                        </div>
                        {subject.name_cn && subject.name_cn !== subject.name && (
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            {subject.name_cn}
                          </div>
                        )}
                      </div>
                      <div className="text-xs text-gray-400 dark:text-gray-500">
                        {typeOptions.find(opt => opt.value === subject.type)?.label}
                      </div>
                      {subject.is_collected && (
                        <div className="text-xs text-green-600 dark:text-green-400 font-medium">
                          已收藏
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <Input
            label="封面图片链接"
            type="url"
            value={coverUrl}
            onChange={(e) => {
              setCoverUrl(e.target.value);
              setImageError(false);
            }}
            placeholder="请输入图片链接（选填）"
            disabled={isSubmitting}
          />

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                类型
              </label>
              <select
                value={type}
                onChange={(e) => setType(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                disabled={isSubmitting}
              >
                {typeOptions.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                状态
              </label>
              <select
                value={status}
                onChange={(e) => setStatus(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                disabled={isSubmitting}
              >
                {statusOptions.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
            label="上映/发售时间"
            type="text"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            placeholder="YYYY-MM-DD"
            disabled={isSubmitting}
          />

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                评分
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="10"
                  step="0.5"
                  value={rate}
                  onChange={(e) => setRate(Number(e.target.value))}
                  className="flex-1 h-2 cursor-pointer appearance-none rounded-lg bg-gray-200 accent-primary dark:bg-gray-700"
                  disabled={isSubmitting}
                />
                <span className="w-12 text-center text-sm font-semibold text-primary dark:text-primary">
                  {rate}
                </span>
              </div>
            </div>
          </div>

          <Input
            label="标签"
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="标签 (逗号分隔)"
            disabled={isSubmitting}
          />

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              吐槽
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="写下你的想法..."
              rows={3}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-white resize-none"
              disabled={isSubmitting}
            />
          </div>
        </div>
      </div>

      <div className="flex gap-3 pt-2">
        <Button
          variant="outline"
          onClick={handleClose}
          disabled={isSubmitting}
          className="flex-1"
        >
          取消
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={isSubmitting || !name.trim()}
          className="flex-1 flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              {selectedSubjectId ? '更新中...' : '添加/修改中...'}
            </>
          ) : (
            selectedSubjectId ? '更新收藏' : '确认添加/修改'
          )}
        </Button>
      </div>
    </Dialog>
  );
}
