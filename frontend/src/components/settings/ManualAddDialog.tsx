"use client";

import { useState, useCallback, useEffect, useRef } from 'react';
import Image from 'next/image';
import { Loader2, Image as ImageIcon, UploadCloud, Search, X, BookMarked, Globe, CheckCircle2, AlertCircle, Star } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { Badge } from '@/components/ui/Badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs';
import { useToast } from '@/components/ui/Toast';
import { useManualAddDialogStore } from '@/lib/manualAddDialogStore';
import { searchSubjects, Subject, updateOrAddCollection, CollectionUpdateData } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';
import { cn } from '@/lib/utils';

interface ManualAddDialogProps {
  isOpen?: boolean;
  onClose?: () => void;
  onSuccess: () => void;
}

interface ValidationError {
  name?: string;
  coverUrl?: string;
  date?: string;
  tags?: string;
}

export function ManualAddDialog({ isOpen: propsIsOpen, onClose: propsOnClose, onSuccess }: ManualAddDialogProps) {
  const { isOpen: storeIsOpen, selectedSubject, closeDialog } = useManualAddDialogStore();
  const { settings } = useSettings();
  
  const isOpen = storeIsOpen ?? propsIsOpen ?? false;
  const onClose = storeIsOpen ? closeDialog : propsOnClose;
  
  const nameInputRef = useRef<HTMLInputElement>(null);
  const coverUrlInputRef = useRef<HTMLInputElement>(null);
  
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
  const [validationErrors, setValidationErrors] = useState<ValidationError>({});
  const { toast } = useToast();

  const [searchResults, setSearchResults] = useState<Subject[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [existingSubjectId, setExistingSubjectId] = useState<number | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [touchedFields, setTouchedFields] = useState<Set<string>>(new Set());
  const [coverUrlValid, setCoverUrlValid] = useState<boolean | null>(null);

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

  const typeSelectOptions = typeOptions.map(opt => ({ label: opt.label, value: opt.value }));
  const statusSelectOptions = statusOptions.map(opt => ({ label: opt.label, value: opt.value }));

  const validateName = useCallback((value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) {
      return '请输入条目标题';
    }
    if (trimmed.length < 1) {
      return '标题至少需要1个字符';
    }
    if (trimmed.length > 200) {
      return '标题不能超过200个字符';
    }
    return null;
  }, []);

  const validateCoverUrl = useCallback((value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    try {
      const url = new URL(trimmed);
      if (!url.protocol.startsWith('http')) {
        return '请输入有效的URL地址';
      }
      if (!/\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(url.pathname)) {
        return '请输入图片链接（jpg, png, gif, webp, bmp）';
      }
      return null;
    } catch {
      return '请输入有效的URL地址';
    }
  }, []);

  const validateDate = useCallback((value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const dateRegex = /^\d{4}(-\d{2}(-\d{2})?)?$/;
    if (!dateRegex.test(trimmed)) {
      return '日期格式不正确，请使用 YYYY-MM-DD 或 YYYY-MM 格式';
    }
    const date = new Date(trimmed);
    if (isNaN(date.getTime())) {
      return '请输入有效的日期';
    }
    return null;
  }, []);

  const validateTags = useCallback((value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const tags = trimmed.split(/[,，]/).map(t => t.trim()).filter(Boolean);
    if (tags.length > 10) {
      return '标签数量不能超过10个';
    }
    const invalidTag = tags.find(t => t.length > 20);
    if (invalidTag) {
      return '每个标签不能超过20个字符';
    }
    return null;
  }, []);

  const handleFieldBlur = useCallback((fieldName: string) => {
    setTouchedFields(prev => new Set([...prev, fieldName]));
  }, []);

  const validateForm = useCallback((): boolean => {
    const errors: ValidationError = {};
    let isValid = true;

    const nameError = validateName(name);
    if (nameError) {
      errors.name = nameError;
      isValid = false;
    }

    const coverUrlError = validateCoverUrl(coverUrl);
    if (coverUrlError) {
      errors.coverUrl = coverUrlError;
      isValid = false;
    }

    const dateError = validateDate(date);
    if (dateError) {
      errors.date = dateError;
      isValid = false;
    }

    const tagsError = validateTags(tags);
    if (tagsError) {
      errors.tags = tagsError;
      isValid = false;
    }

    setValidationErrors(errors);
    return isValid;
  }, [name, coverUrl, date, tags, validateName, validateCoverUrl, validateDate, validateTags]);

  const handleSelectSubject = useCallback((subject: Subject) => {
    setShowSearchResults(false);

    setName(subject.name);
    setCoverUrl(subject.cover_url || '');
    setType(subject.type);
    setDate(subject.date || '');

    setExistingSubjectId(subject.id);

    if (subject.is_collected && subject.collection_info) {
      setRate(subject.collection_info.rate || 0);
      setComment(subject.collection_info.comment || '');
      setTags(Array.isArray(subject.collection_info.tags) ? subject.collection_info.tags.join(', ') : '');
      setStatus(statusStringToNumber(subject.collection_info.status));
      setIsEditMode(true);
    } else {
      setRate(0);
      setComment('');
      setTags('');
      setStatus(1);
      setIsEditMode(false);
    }
  }, [statusStringToNumber]);

  useEffect(() => {
    if (selectedSubject && storeIsOpen) {
      handleSelectSubject(selectedSubject);
    }
  }, [selectedSubject, storeIsOpen, handleSelectSubject]);

  const resetForm = useCallback(() => {
    setName('');
    setCoverUrl('');
    setType(2);
    setStatus(1);
    setRate(0);
    setComment('');
    setDate('');
    setTags('');
    setSearchResults([]);
    setIsSearching(false);
    setSelectedSubjectId(null);
    setShowSearchResults(false);
    setValidationErrors({});
    setTouchedFields(new Set());
    setCoverUrlValid(null);
  }, []);

  useEffect(() => {
    if (isOpen) {
      resetForm();
      setTimeout(() => {
        nameInputRef.current?.focus();
      }, 100);
    }
  }, [isOpen, resetForm]);

  useEffect(() => {
    if (coverUrl && touchedFields.has('coverUrl')) {
      const error = validateCoverUrl(coverUrl);
      setCoverUrlValid(!error);
    } else {
      setCoverUrlValid(null);
    }
  }, [coverUrl, touchedFields, validateCoverUrl]);

  const handleSearch = useCallback(async () => {
    if (name.length < 2) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }

    setIsSearching(true);
    try {
      // 使用新的searchSubjects方法，总是使用mixed模式获取所有搜索结果
      const results = await searchSubjects(name, type, 'mixed');
      
      // 按收藏状态排序，已收藏的条目排在前面
      const sortedResults = [...results].sort((a, b) => {
        // 已收藏的条目排在前面
        if (a.is_collected && !b.is_collected) return -1;
        if (!a.is_collected && b.is_collected) return 1;
        // 相同收藏状态的条目按id排序（稳定排序）
        return (a.id || 0) - (b.id || 0);
      });
      
      setSearchResults(sortedResults);
      setShowSearchResults(sortedResults.length > 0);
    } catch (error) {
      console.error('Search error:', error);
      setSearchResults([]);
      setShowSearchResults(false);
      toast({
        type: 'error',
        message: '搜索失败，请重试'
      });
    } finally {
      setIsSearching(false);
    }
  }, [name, type, toast]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSearch();
    }
  }, [handleSearch]);

  const handleClearSelection = useCallback(() => {
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
    setValidationErrors({});
    setTouchedFields(new Set());
    setCoverUrlValid(null);
    
    setTimeout(() => {
      nameInputRef.current?.focus();
    }, 0);
  }, []);

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast({
        type: 'error',
        message: '请输入条目标题'
      });
      return;
    }

    if (!validateForm()) {
      toast({
        type: 'error',
        message: '请检查表单中的错误'
      });
      return;
    }

    setIsSubmitting(true);

    try {
      const getTagsArray = (val: string) => {
        return (val || "").split(/[,，]/).map(t => t.trim()).filter(Boolean);
      };

      const collectionData: CollectionUpdateData = {
        status: Number(status),
        rate: Number(rate || 0),
        comment: comment || "",
        private: false,
        tags: getTagsArray(tags)
      };

      let response;
      if (existingSubjectId) {
        // 更新或添加现有条目的收藏
        response = await updateOrAddCollection(existingSubjectId, collectionData);
      } else {
        // 对于新条目，我们需要先创建条目再添加收藏
        // 注意：根据后端文档，updateOrAddCollection可以同时处理条目创建和收藏添加
        const subjectData = {
          name: name.trim(),
          name_cn: name.trim(), // 暂时使用相同的名称，后续可以添加中文名输入
          type: Number(type),
          cover_url: coverUrl.trim(),
          release_date: date || "",
          publish_date: date || "",
          tags: getTagsArray(tags)
        };
        
        // 这里使用一个临时的subject_id，后端会处理实际的创建
        // 注意：根据后端文档，当subject_id不存在时，会创建新条目
        // 但这里我们没有实际的subject_id，所以需要调整
        // 暂时先使用一个特殊值，后续可以根据后端实际实现调整
        // 注意：这里可能需要调整，因为后端API可能不支持直接创建条目
        throw new Error('无法直接创建新条目，请先搜索现有条目');
      }

      toast({
        type: 'success',
        message: isEditMode ? '更新成功！' : '添加成功！'
      });

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

  const handleClose = useCallback(() => {
    resetForm();
    if (onClose) {
      onClose();
    }
  }, [resetForm, onClose]);

  const handleNameChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setName(e.target.value);
    if (touchedFields.has('name')) {
      const error = validateName(e.target.value);
      setValidationErrors(prev => ({ ...prev, name: error || undefined }));
    }
  }, [touchedFields, validateName]);

  const handleCoverUrlChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setCoverUrl(e.target.value);
    if (touchedFields.has('coverUrl')) {
      const error = validateCoverUrl(e.target.value);
      setValidationErrors(prev => ({ ...prev, coverUrl: error || undefined }));
    }
  }, [touchedFields, validateCoverUrl]);

  const handleDateChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setDate(e.target.value);
    if (touchedFields.has('date')) {
      const error = validateDate(e.target.value);
      setValidationErrors(prev => ({ ...prev, date: error || undefined }));
    }
  }, [touchedFields, validateDate]);

  const handleTagsChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTags(e.target.value);
    if (touchedFields.has('tags')) {
      const error = validateTags(e.target.value);
      setValidationErrors(prev => ({ ...prev, tags: error || undefined }));
    }
  }, [touchedFields, validateTags]);

  return (
    <Dialog isOpen={isOpen} onClose={handleClose} title="条目信息">
      <div className="grid gap-8 py-6 md:grid-cols-[260px_1fr]">
        <div 
          className={cn(
            "relative w-full overflow-hidden rounded-lg border self-start shadow-md transition-all duration-300",
            coverUrlValid === true ? "border-green-300 dark:border-green-600" :
            coverUrlValid === false ? "border-red-300 dark:border-red-600" :
            "border-gray-200 dark:border-gray-700",
            coverUrl ? "bg-gray-100 dark:bg-gray-800" : "bg-gray-100 dark:bg-gray-800"
          )} 
          style={{ aspectRatio: '2/3' }} 
        >
          {coverUrl ? (
            <>
              <Image 
                src={coverUrl} 
                alt="Blur Background" 
                fill
                className="absolute inset-0 h-full w-full object-cover blur-xl opacity-40 scale-110" 
                unoptimized
              />
              <Image 
                src={coverUrl} 
                alt="Cover" 
                fill
                className="relative h-full w-full object-contain z-10" 
                unoptimized
              />
              {coverUrlValid === true && (
                <div className="absolute top-2 right-2 z-20">
                  <CheckCircle2 className="w-5 h-5 text-green-500 bg-white/90 rounded-full" />
                </div>
              )}
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
                  <div className="relative h-16 w-12 flex-shrink-0">
                    <Image
                      src={coverUrl}
                      alt={name}
                      fill
                      className="object-cover rounded shadow-sm"
                      unoptimized
                    />
                  </div>
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
                  type="button"
                >
                  <X className="w-3.5 h-3.5" />
                  更换
                </button>
              </div>
            </div>
          ) : (
            <div className="relative">
              <div className="flex gap-2 mt-4">
                <div className="relative flex-1">
                  <Input
                    label="标题"
                    type="text"
                    value={name}
                    onChange={handleNameChange}
                    onBlur={() => handleFieldBlur('name')}
                    placeholder="搜索条目（已收藏的条目会优先显示）"
                    disabled={isSubmitting}
                    required
                    autoFocus
                    ref={nameInputRef}
                    onKeyDown={handleKeyDown}
                    error={touchedFields.has('name') ? validationErrors.name : undefined}
                  />
                </div>
                <Button
                  onClick={handleSearch}
                  disabled={isSearching || name.length < 2}
                  className="mt-[22px]"
                  type="button"
                >
                  {isSearching ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Search className="w-4 h-4" />
                  )}
                </Button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                搜索所有可用条目，已收藏的条目会优先显示
              </p>
              
              {showSearchResults && searchResults.length > 0 && (
                <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800 max-h-64 overflow-y-auto">
                  {searchResults.map((subject, index) => (
                    <button
                      key={subject.id ? String(subject.id) : `subject-${index}-${subject.name}`}
                      onClick={() => handleSelectSubject(subject)}
                      className="flex w-full items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-0"
                      type="button"
                    >
                      {subject.cover_url && (
                        <div className="relative h-12 w-8 flex-shrink-0">
                          <Image
                            src={subject.cover_url}
                            alt={subject.name}
                            fill
                            className="object-cover rounded"
                            unoptimized
                          />
                        </div>
                      )}
                      <div className="flex-1 text-left">
                        <div className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-1">
                          {subject.name}
                          {subject.is_collected && (
                            <svg className="w-4 h-4 text-yellow-400 fill-yellow-400" viewBox="0 0 20 20" aria-hidden="true">
                              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                            </svg>
                          )}
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
                        <Badge variant="success" showDot={false}>
                          已收藏
                        </Badge>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div>
            <label htmlFor="cover-url-input" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              封面图片链接
            </label>
            <div className="relative">
              <input
                ref={coverUrlInputRef}
                id="cover-url-input"
                type="url"
                value={coverUrl}
                onChange={handleCoverUrlChange}
                onBlur={() => handleFieldBlur('coverUrl')}
                placeholder="请输入图片链接（选填）"
                disabled={isSubmitting}
                className={cn(
                  "w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-gray-800 dark:text-white transition-colors",
                  touchedFields.has('coverUrl') && validationErrors.coverUrl
                    ? "border-red-300 dark:border-red-600 focus:ring-red-500"
                    : "border-gray-300 dark:border-gray-600"
                )}
                aria-invalid={!!(touchedFields.has('coverUrl') && validationErrors.coverUrl)}
              />
              {touchedFields.has('coverUrl') && validationErrors.coverUrl && (
                <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-4 h-4" />
                  {validationErrors.coverUrl}
                </p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Select
              label="类型"
              options={typeSelectOptions}
              value={String(type)}
              onChange={(e) => setType(Number(e.target.value))}
              disabled={isSubmitting}
            />

            <Select
              label="状态"
              options={statusSelectOptions}
              value={String(status)}
              onChange={(e) => setStatus(Number(e.target.value))}
              disabled={isSubmitting}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="date-input" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                上映/发售时间
              </label>
              <input
                id="date-input"
                type="text"
                value={date}
                onChange={handleDateChange}
                onBlur={() => handleFieldBlur('date')}
                placeholder="YYYY-MM-DD"
                disabled={isSubmitting}
                className={cn(
                  "w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-gray-800 dark:text-white transition-colors",
                  touchedFields.has('date') && validationErrors.date
                    ? "border-red-300 dark:border-red-600 focus:ring-red-500"
                    : "border-gray-300 dark:border-gray-600"
                )}
                aria-invalid={!!(touchedFields.has('date') && validationErrors.date)}
              />
              {touchedFields.has('date') && validationErrors.date && (
                <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-4 h-4" />
                  {validationErrors.date}
                </p>
              )}
            </div>

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
                  aria-label="评分"
                />
                <div className="flex items-center gap-1 w-12 justify-center">
                  <Star className={cn(
                    "w-4 h-4",
                    rate > 0 ? "text-yellow-400 fill-yellow-400" : "text-gray-400"
                  )} />
                  <span className="text-sm font-semibold text-primary dark:text-primary">
                    {rate}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div>
            <label htmlFor="tags-input" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              标签
            </label>
            <textarea
              id="tags-input"
              value={tags}
              onChange={handleTagsChange}
              onBlur={() => handleFieldBlur('tags')}
              placeholder="标签 (逗号分隔)"
              disabled={isSubmitting}
              rows={2}
              className={cn(
                "w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-gray-800 dark:text-white transition-colors resize-none",
                touchedFields.has('tags') && validationErrors.tags
                  ? "border-red-300 dark:border-red-600 focus:ring-red-500"
                  : "border-gray-300 dark:border-gray-600"
              )}
              aria-invalid={!!(touchedFields.has('tags') && validationErrors.tags)}
            />
            {touchedFields.has('tags') && validationErrors.tags && (
              <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1">
                <AlertCircle className="w-4 h-4" />
                {validationErrors.tags}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="comment-input" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              吐槽
            </label>
            <Textarea
              id="comment-input"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="写下你的想法..."
              rows={3}
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
          type="button"
        >
          取消
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={isSubmitting || !name.trim()}
          className="flex-1"
          type="button"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              提交中...
            </>
          ) : (
            isEditMode ? '更新' : '添加'
          )}
        </Button>
      </div>
    </Dialog>
  );
}
