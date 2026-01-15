'use client';

import { useState, useCallback, useEffect } from 'react';
import { Save, X, Loader2 } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Select } from '@/components/ui/Select';
import { useToast } from '@/components/ui/Toast';
import { updateOrAddCollection } from '@/lib/api';
import type { Subject, BangumiUser } from '@/lib/api';

interface CollectionAddFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  subject?: Subject | null;
}

// 收藏状态选项
const STATUS_OPTIONS = [
  { value: '1', label: '想看' },
  { value: '2', label: '看过' },
  { value: '3', label: '在看' },
  { value: '4', label: '搁置' },
  { value: '5', label: '抛弃' }
];

// 条目类型选项
const SUBJECT_TYPE_OPTIONS = [
  { value: '1', label: '书籍' },
  { value: '2', label: '动画' },
  { value: '3', label: '音乐' },
  { value: '4', label: '游戏' },
  { value: '6', label: '三次元' }
];

export function CollectionAddForm({ isOpen, onClose, onSuccess, subject }: CollectionAddFormProps) {
  const { toast } = useToast();
  const [isSaving, setIsSaving] = useState(false);
  const [isNewSubject, setIsNewSubject] = useState(!subject);
  
  // 根据 subject 数据自动填充表单
  const [formData, setFormData] = useState({
    status: '2',
    rate: subject?.score || 0,
    comment: subject?.summary || '',
    private: false,
    tags: subject?.tags?.join(', ') || ''
  });
  
  // 新条目表单数据
  const [subjectData, setSubjectData] = useState({
    name: subject?.name || '',
    name_cn: subject?.name_cn || '',
    type: subject?.type?.toString() || '2',
    cover_url: subject?.cover_url || '',
    release_date: subject?.date || '',
    publish_date: subject?.date || ''
  });

  // 处理收藏表单输入变化
  const handleCollectionInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const target = e.target as HTMLInputElement;
    const { name, value, type } = target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? target.checked : value
    }));
  }, []);

  // 处理收藏选择变化
  const handleCollectionSelectChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
  }, []);

  // 处理新条目表单输入变化
  const handleSubjectInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setSubjectData(prev => ({
      ...prev,
      [name]: value
    }));
  }, []);

  // 处理新条目选择变化
  const handleSubjectSelectChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setSubjectData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
  }, []);

  // 日期格式验证
  const validateDateFormat = (date: string): boolean => {
    if (!date) return true;
    const regex = /^\d{4}-\d{2}-\d{2}$/;
    if (!regex.test(date)) return false;
    
    const d = new Date(date);
    return d instanceof Date && !isNaN(d.getTime());
  };

  // 检查日期冲突
  const checkDateConflict = (releaseDate: string, publishDate: string): boolean => {
    if (!releaseDate || !publishDate) return false;
    
    const release = new Date(releaseDate);
    const publish = new Date(publishDate);
    
    return release > publish;
  };

  // 处理保存收藏
  const handleSaveCollection = useCallback(async () => {
    // 表单验证
    if (!formData.status) {
      toast({
        type: 'error',
        message: '请选择收藏状态'
      });
      return;
    }
    
    // 如果是新条目，验证条目信息
    if (isNewSubject) {
      if (!subjectData.name) {
        toast({
          type: 'error',
          message: '请输入条目名称'
        });
        return;
      }
      
      if (!subjectData.type) {
        toast({
          type: 'error',
          message: '请选择条目类型'
        });
        return;
      }
      
      if (!subjectData.cover_url) {
        toast({
          type: 'error',
          message: '请输入封面URL'
        });
        return;
      }
      
      // 验证日期格式
      if (!validateDateFormat(subjectData.release_date)) {
        toast({
          type: 'error',
          message: '上映日期格式错误，请使用 YYYY-MM-DD 格式'
        });
        return;
      }
      
      if (!validateDateFormat(subjectData.publish_date)) {
        toast({
          type: 'error',
          message: '发售日期格式错误，请使用 YYYY-MM-DD 格式'
        });
        return;
      }
      
      // 检查日期冲突
      if (checkDateConflict(subjectData.release_date, subjectData.publish_date)) {
        toast({
          type: 'error',
          message: '上映时间不能晚于发售时间'
        });
        return;
      }
    }
    
    setIsSaving(true);
    try {
      // 准备API调用数据
      const collectionData = {
        status: parseInt(formData.status),
        rate: formData.rate > 0 ? formData.rate : 0,
        comment: formData.comment,
        private: formData.private,
        tags: formData.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean)
      };
      
      // 调用API
      if (subject && subject.id) {
        // 更新现有条目
        await updateOrAddCollection(subject.id, collectionData);
        toast({
          type: 'success',
          message: `成功添加收藏: ${subject.name_cn || subject.name}`
        });
      } else {
        // 创建新条目
        const subjectToCreate = {
          name: subjectData.name,
          name_cn: subjectData.name_cn,
          type: parseInt(subjectData.type),
          cover_url: subjectData.cover_url,
          release_date: subjectData.release_date,
          publish_date: subjectData.publish_date,
          tags: [subjectData.name_cn || subjectData.name],
          status: parseInt(formData.status),
          rate: formData.rate > 0 ? formData.rate : 0,
          comment: formData.comment
        };
        
        await updateOrAddCollection(0, collectionData, subjectToCreate);
        toast({
          type: 'success',
          message: `成功创建新收藏: ${subjectData.name_cn || subjectData.name}`
        });
      }
      
      onSuccess?.();
      onClose();
    } catch (error) {
      console.error('Error adding collection:', error);
      toast({
        type: 'error',
        message: '添加收藏失败，请稍后重试'
      });
    } finally {
      setIsSaving(false);
    }
  }, [subject, formData, subjectData, isNewSubject, toast, onSuccess, onClose]);



  return (
    <Dialog 
      isOpen={isOpen} 
      onClose={onClose} 
      title={subject ? "添加收藏" : "创建新条目"}
    >
      <div className="space-y-4">
        {/* 条目信息（如果是新条目） */}
        {isNewSubject && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium">条目名称 <span className="text-red-500">*</span></label>
                <Input
                  type="text"
                  name="name"
                  value={subjectData.name}
                  onChange={handleSubjectInputChange}
                  disabled={isSaving}
                  placeholder="请输入条目名称"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium">中文名称</label>
                <Input
                  type="text"
                  name="name_cn"
                  value={subjectData.name_cn}
                  onChange={handleSubjectInputChange}
                  disabled={isSaving}
                  placeholder="请输入中文名称"
                />
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium">条目类型 <span className="text-red-500">*</span></label>
                <Select
                  name="type"
                  value={subjectData.type}
                  onChange={handleSubjectSelectChange}
                  disabled={isSaving}
                  options={SUBJECT_TYPE_OPTIONS}
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium">封面URL <span className="text-red-500">*</span></label>
                <Input
                  type="text"
                  name="cover_url"
                  value={subjectData.cover_url}
                  onChange={handleSubjectInputChange}
                  disabled={isSaving}
                  placeholder="请输入封面URL"
                />
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium">上映日期</label>
                <Input
                  type="text"
                  name="release_date"
                  value={subjectData.release_date}
                  onChange={handleSubjectInputChange}
                  disabled={isSaving}
                  placeholder="YYYY-MM-DD"
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium">发售日期</label>
                <Input
                  type="text"
                  name="publish_date"
                  value={subjectData.publish_date}
                  onChange={handleSubjectInputChange}
                  disabled={isSaving}
                  placeholder="YYYY-MM-DD"
                />
              </div>
            </div>
          </div>
        )}
        
        {/* 收藏信息 */}
        <div className="space-y-4 pt-2 border-t">
          <div className="space-y-2">
            <label className="block text-sm font-medium">收藏状态 <span className="text-red-500">*</span></label>
            <Select
              name="status"
              value={formData.status}
              onChange={handleCollectionSelectChange}
              disabled={isSaving}
              options={STATUS_OPTIONS}
            />
          </div>
          
          <div className="space-y-2">
            <label className="block text-sm font-medium">评分 (0-10)</label>
            <Input
              type="number"
              name="rate"
              min="0"
              max="10"
              step="1"
              value={formData.rate}
              onChange={handleCollectionInputChange}
              disabled={isSaving}
              placeholder="请输入评分"
            />
          </div>
          
          <div className="space-y-2">
            <label className="block text-sm font-medium">评论</label>
            <Textarea
              name="comment"
              value={formData.comment}
              onChange={handleCollectionInputChange}
              disabled={isSaving}
              placeholder="请输入评论"
              rows={4}
            />
          </div>
          
          <div className="space-y-2">
            <label className="block text-sm font-medium">标签 (用逗号分隔)</label>
            <Input
              type="text"
              name="tags"
              value={formData.tags}
              onChange={handleCollectionInputChange}
              disabled={isSaving}
              placeholder="例如: 动画, 热血, 冒险"
            />
          </div>
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="private"
              name="private"
              checked={formData.private}
              onChange={handleCollectionInputChange}
              disabled={isSaving}
            />
            <label htmlFor="private" className="text-sm font-medium">设为私有</label>
          </div>
        </div>
        
        {/* 操作按钮 */}
        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button
            variant="outline"
            onClick={onClose}
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
    </Dialog>
  );
}