"use client";

import { useState, useCallback, useEffect } from 'react';
import { Search, Loader2, Plus, Edit3, Save, X } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/components/ui/Toast';
import { searchSubjects, updateOrAddCollection, getUserCollections } from '@/lib/api';
import type { Subject, CollectionWithSubject } from '@/lib/api';

interface CollectionManagerProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

// 收藏状态选项
const STATUS_OPTIONS = [
  { value: '1', label: '想看' },
  { value: '2', label: '看过' },
  { value: '3', label: '在看' },
  { value: '4', label: '搁置' },
  { value: '5', label: '抛弃' }
];

export function CollectionManager({ isOpen, onClose, onSuccess }: CollectionManagerProps) {
  const { toast } = useToast();
  
  // 搜索相关状态
  const [keyword, setKeyword] = useState('');
  const [results, setResults] = useState<Subject[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  
  // 表单相关状态
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState<Subject | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  // 收藏信息
  const [formData, setFormData] = useState({
    status: 2,
    rate: 0,
    comment: '',
    tags: '',
    private: false
  });
  
  // 获取用户收藏列表，用于检查搜索结果是否已收藏
  const [userCollections, setUserCollections] = useState<Map<number, CollectionWithSubject>>(new Map());
  const [isLoadingCollections, setIsLoadingCollections] = useState(false);
  
  // 加载用户收藏列表
  const loadUserCollections = useCallback(async () => {
    setIsLoadingCollections(true);
    try {
      const result = await getUserCollections(2, undefined, undefined, 1000, 0, 'updated_at');
      const collectionsMap = new Map<number, CollectionWithSubject>();
      result.items.forEach(item => {
        if (item.subject.id) {
          collectionsMap.set(item.subject.id, item);
        }
      });
      setUserCollections(collectionsMap);
    } catch (error) {
      console.error('Error loading user collections:', error);
      toast({
        type: 'error',
        message: '加载收藏列表失败，请稍后重试'
      });
    } finally {
      setIsLoadingCollections(false);
    }
  }, [toast]);
  
  // 组件打开时加载用户收藏列表
  useEffect(() => {
    if (isOpen) {
      loadUserCollections();
    }
  }, [isOpen, loadUserCollections]);
  
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
  
  // 处理键盘事件
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }, [handleSearch]);
  
  // 处理添加收藏
  const handleAddCollection = useCallback((subject: Subject) => {
    setSelectedSubject(subject);
    setIsEditing(false);
    // 重置表单数据
    setFormData({
      status: 2,
      rate: 0,
      comment: '',
      tags: subject.tags?.join(', ') || '',
      private: false
    });
    setIsFormOpen(true);
  }, []);
  
  // 处理修改收藏
  const handleEditCollection = useCallback((subject: Subject) => {
    setSelectedSubject(subject);
    setIsEditing(true);
    
    // 获取用户收藏信息并回填表单
    const userCollection = userCollections.get(subject.id);
    if (userCollection && userCollection.collection) {
      setFormData({
        status: userCollection.collection.status || 2,
        rate: userCollection.collection.rate || 0,
        comment: userCollection.collection.comment || '',
        tags: Array.isArray(userCollection.collection.tags) ? userCollection.collection.tags.join(', ') : '',
        private: userCollection.collection.private || false
      });
    } else {
      // 如果没有找到收藏信息，使用默认值
      setFormData({
        status: 2,
        rate: 0,
        comment: '',
        tags: subject.tags?.join(', ') || '',
        private: false
      });
    }
    
    setIsFormOpen(true);
  }, [userCollections]);
  
  // 处理表单输入变化
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const target = e.target as HTMLInputElement;
    const { name, value, type } = target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? target.checked : value
    }));
  }, []);
  
  // 处理选择变化
  const handleSelectChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: parseInt(e.target.value)
    }));
  }, []);
  
  // 处理保存收藏
  const handleSaveCollection = useCallback(async () => {
    if (!selectedSubject) return;
    
    setIsSaving(true);
    try {
      const collectionData = {
        status: formData.status,
        rate: formData.rate > 0 ? formData.rate : 0,
        comment: formData.comment,
        private: formData.private,
        tags: formData.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean)
      };
      
      // 准备subjectData，当收藏不存在时需要传递
      const subjectData = {
        name: selectedSubject.name,
        name_cn: selectedSubject.name_cn || selectedSubject.name,
        type: selectedSubject.type,
        cover_url: selectedSubject.cover_url,
        release_date: selectedSubject.date || '',
        publish_date: selectedSubject.date || '',
        tags: selectedSubject.tags || [],
        status: formData.status,
        rate: formData.rate > 0 ? formData.rate : 0,
        comment: formData.comment
      };
      
      // 调用API保存收藏信息
      await updateOrAddCollection(selectedSubject.id, collectionData, subjectData);
      
      toast({
        type: 'success',
        message: isEditing 
          ? `成功更新收藏: ${selectedSubject.name_cn || selectedSubject.name}`
          : `成功添加收藏: ${selectedSubject.name_cn || selectedSubject.name}`
      });
      
      // 刷新用户收藏列表
      loadUserCollections();
      // 关闭表单
      setIsFormOpen(false);
      setSelectedSubject(null);
      // 通知父组件操作成功
      onSuccess?.();
    } catch (error) {
      console.error('Error saving collection:', error);
      toast({
        type: 'error',
        message: isEditing ? '更新收藏失败，请稍后重试' : '添加收藏失败，请稍后重试'
      });
    } finally {
      setIsSaving(false);
    }
  }, [selectedSubject, formData, isEditing, toast, loadUserCollections, onSuccess]);
  
  // 处理取消操作
  const handleCancel = useCallback(() => {
    setIsFormOpen(false);
    setSelectedSubject(null);
  }, []);
  
  // 检查条目是否已被收藏
  const isSubjectCollected = useCallback((subjectId: number) => {
    return userCollections.has(subjectId);
  }, [userCollections]);
  
  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="添加/修改收藏">
      <div className="space-y-4">
        {/* 搜索表单 */}
        <div className="flex gap-2">
          <Input
            type="text"
            placeholder="输入动画名称搜索..."
            value={keyword}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setKeyword(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSearching || isLoadingCollections}
            className="flex-1"
          />
          <Button
            onClick={handleSearch}
            disabled={isSearching || isLoadingCollections || !keyword.trim()}
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
          {isLoadingCollections ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <span className="ml-2">加载收藏列表中...</span>
            </div>
          ) : isSearching ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <span className="ml-2">搜索中...</span>
            </div>
          ) : results.length > 0 ? (
            <div className="space-y-2">
              {results.map((subject, index) => {
                const collected = isSubjectCollected(subject.id);
                return (
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
                        {collected && (
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
                          {collected && (
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
                    <div className="flex gap-2">
                      {collected ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleEditCollection(subject)}
                        >
                          <Edit3 className="w-4 h-4 mr-1" />
                          修改
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => handleAddCollection(subject)}
                        >
                          <Plus className="w-4 h-4 mr-1" />
                          添加
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
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
        
        {/* 添加/修改收藏表单 */}
        {isFormOpen && selectedSubject && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-xl font-medium">
                    {isEditing ? '修改收藏' : '添加收藏'}
                  </h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCancel}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
                
                {/* 条目基本信息 */}
                <div className="flex items-center gap-4 mb-6 p-4 border rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div className="w-20 h-28 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0">
                    {selectedSubject.cover_url && (
                      <img
                        src={selectedSubject.cover_url}
                        alt={selectedSubject.name}
                        className="w-full h-full object-cover rounded"
                      />
                    )}
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium">
                      {selectedSubject.name_cn || selectedSubject.name}
                    </h4>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {selectedSubject.name}
                    </p>
                    {selectedSubject.score && (
                      <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                        评分: {selectedSubject.score}
                      </p>
                    )}
                  </div>
                </div>
                
                {/* 收藏信息表单 */}
                <div className="space-y-4">
                  {/* 收藏状态 */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium">收藏状态</label>
                    <Select
                      name="status"
                      value={formData.status.toString()}
                      onChange={handleSelectChange}
                      disabled={isSaving}
                      options={STATUS_OPTIONS}
                    />
                  </div>
                  
                  {/* 评分 */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium">评分 (0-10)</label>
                    <Input
                      type="number"
                      name="rate"
                      min="0"
                      max="10"
                      step="1"
                      value={formData.rate}
                      onChange={handleInputChange}
                      disabled={isSaving}
                      placeholder="请输入评分"
                    />
                  </div>
                  
                  {/* 评论 */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium">评论</label>
                    <Textarea
                      name="comment"
                      value={formData.comment}
                      onChange={handleInputChange}
                      disabled={isSaving}
                      placeholder="请输入评论"
                      rows={4}
                    />
                  </div>
                  
                  {/* 标签 */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium">标签 (用逗号分隔)</label>
                    <Input
                      type="text"
                      name="tags"
                      value={formData.tags}
                      onChange={handleInputChange}
                      disabled={isSaving}
                      placeholder="例如: 动画, 热血, 冒险"
                    />
                  </div>
                  
                  {/* 私有设置 */}
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="private"
                      name="private"
                      checked={formData.private}
                      onChange={handleInputChange}
                      disabled={isSaving}
                    />
                    <label htmlFor="private" className="text-sm font-medium">设为私有</label>
                  </div>
                  
                  {/* 操作按钮 */}
                  <div className="flex justify-end gap-2 pt-4 border-t">
                    <Button
                      variant="outline"
                      onClick={handleCancel}
                      disabled={isSaving}
                    >
                      取消
                    </Button>
                    <Button
                      onClick={handleSaveCollection}
                      disabled={isSaving}
                    >
                      {isSaving ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4 mr-2" />
                      )}
                      保存
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}