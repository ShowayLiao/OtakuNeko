"use client";

import { useState, useCallback, useEffect } from 'react';
import { Edit3, Loader2, Save, Trash2, X } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Select } from '@/components/ui/Select';
import { useToast } from '@/components/ui/Toast';
import { getUserCollections, updateOrAddCollection } from '@/lib/api';
import type { CollectionWithSubject } from '@/lib/api';

interface CollectionEditFormProps {
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

export function CollectionEditForm({ isOpen, onClose, onSuccess }: CollectionEditFormProps) {
  const { toast } = useToast();
  const [collections, setCollections] = useState<CollectionWithSubject[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState<CollectionWithSubject | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState({
    status: 2,
    rate: 0,
    comment: '',
    tags: '',
    private: false
  });

  // 初始化表单数据
  useEffect(() => {
    if (selectedCollection && selectedCollection.collection) {
      setFormData({
        status: selectedCollection.collection.status || 2,
        rate: selectedCollection.collection.rate || 0,
        comment: selectedCollection.collection.comment || '',
        tags: Array.isArray(selectedCollection.collection.tags) ? selectedCollection.collection.tags.join(', ') : '',
        private: selectedCollection.collection.private || false
      });
    }
  }, [selectedCollection]);

  // 获取收藏列表
  const fetchCollections = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await getUserCollections(2, undefined, undefined, 50, 0, 'updated_at');
      setCollections(result.items);
      
      if (result.items.length === 0) {
        toast({
          type: 'info',
          message: '没有找到收藏记录'
        });
      }
    } catch (error) {
      console.error('Error fetching collections:', error);
      toast({
        type: 'error',
        message: '获取收藏列表失败，请稍后重试'
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  // 获取收藏列表
  useEffect(() => {
    if (isOpen) {
      fetchCollections();
    }
  }, [isOpen, fetchCollections]);

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
    if (!selectedCollection) return;
    
    setIsSaving(true);
    try {
      const collectionData = {
        status: formData.status,
        rate: formData.rate > 0 ? formData.rate : 0,
        comment: formData.comment,
        private: formData.private,
        tags: formData.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean)
      };
      
      // 调用API并获取返回的收藏信息
      const response = await updateOrAddCollection(selectedCollection.subject.id, collectionData);
      
      toast({
        type: 'success',
        message: `成功更新收藏: ${selectedCollection.subject.name_cn || selectedCollection.subject.name}`
      });
      
      // 使用返回的收藏信息更新表单数据
      setFormData({
        status: response.status,
        rate: response.rate,
        comment: response.comment,
        tags: response.tags.join(', '),
        private: response.private
      });
      
      // 刷新收藏列表，确保显示最新数据
      fetchCollections();
      setSelectedCollection(null);
      onSuccess?.();
    } catch (error) {
      console.error('Error updating collection:', error);
      toast({
        type: 'error',
        message: '更新收藏失败，请稍后重试'
      });
    } finally {
      setIsSaving(false);
    }
  }, [selectedCollection, formData, toast, fetchCollections, onSuccess]);

  // 处理取消编辑
  const handleCancelEdit = useCallback(() => {
    setSelectedCollection(null);
    setFormData({
      status: 2,
      rate: 0,
      comment: '',
      tags: '',
      private: false
    });
  }, []);

  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="修改收藏">
      <div className="space-y-4">
        {/* 收藏列表 */}
        {!selectedCollection ? (
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <h3 className="font-medium">收藏列表</h3>
              <Button
                size="sm"
                variant="outline"
                onClick={fetchCollections}
                disabled={isLoading}
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                刷新
              </Button>
            </div>
            
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
                <span className="ml-2">加载中...</span>
              </div>
            ) : collections.length > 0 ? (
              <div className="max-h-96 overflow-y-auto space-y-2">
                {collections.map((item, index) => (
                  <div key={item.collection?.id || `no-collection-${index}`} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-16 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0">
                        {item.subject.cover_url && (
                          <img
                            src={item.subject.cover_url}
                            alt={item.subject.name}
                            className="w-full h-full object-cover rounded"
                            loading="lazy"
                          />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium truncate">
                          {item.subject.name_cn || item.subject.name}
                        </h4>
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                          {item.subject.name}
                        </p>
                        <div className="flex items-center gap-2 mt-1 text-xs">
                          {item.collection ? (
                            <>
                              <span className="text-primary">
                                {STATUS_OPTIONS.find(opt => opt.value === item.collection.status?.toString())?.label || '未知'}
                              </span>
                              {item.collection.rate > 0 && (
                                <span className="text-yellow-600 dark:text-yellow-400">
                                  评分: {item.collection.rate}
                                </span>
                              )}
                            </>
                          ) : (
                            <span className="text-gray-500 dark:text-gray-400">
                              无收藏信息
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => setSelectedCollection(item)}
                    >
                      <Edit3 className="w-4 h-4 mr-1" />
                      编辑
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                没有找到收藏记录
              </div>
            )}
          </div>
        ) : (
          /* 编辑表单 */
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">编辑收藏</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCancelEdit}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
            
            {/* 条目信息 */}
            <div className="p-3 border rounded-lg bg-gray-50 dark:bg-gray-800">
              <div className="flex items-center gap-3">
                <div className="w-16 h-20 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0">
                  {selectedCollection.subject.cover_url && (
                    <img
                      src={selectedCollection.subject.cover_url}
                      alt={selectedCollection.subject.name}
                      className="w-full h-full object-cover rounded"
                      loading="lazy"
                    />
                  )}
                </div>
                <div className="flex-1">
                  <h4 className="font-medium">
                    {selectedCollection.subject.name_cn || selectedCollection.subject.name}
                  </h4>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {selectedCollection.subject.name}
                  </p>
                </div>
              </div>
            </div>
            
            {/* 状态选择 */}
            <div className="space-y-2">
              <label className="block text-sm font-medium">状态</label>
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
                onClick={handleCancelEdit}
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
        )}
      </div>
    </Dialog>
  );
}

// 刷新图标组件
function RefreshCw(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21.5 2v6h-6" />
      <path d="M2 21.5h6v-6" />
      <path d="M2 2v8h8" />
      <path d="M21.5 21.5h-8v-8" />
      <path d="m2 22 4.9-4.9" />
      <path d="m22 2-4.9 4.9" />
    </svg>
  );
}
