"use client";

import { useState, useCallback, useEffect } from 'react';
import { UploadCloud, FileText, X, Loader2 } from 'lucide-react';
import { Dialog } from './ui/Dialog';
import { Button } from './ui/Button';
import { useToast } from './ui/Toast';
import { uploadDoubanFile } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';

interface DoubanImportDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function DoubanImportDialog({ isOpen, onClose, onSuccess }: DoubanImportDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState<string>('');
  const { toast } = useToast();
  const { settings, updateSettings } = useSettings();

  useEffect(() => {
    if (isOpen) {
      if (settings.username) {
        setUsername(settings.username);
      } else {
        setUsername('');
      }
    }
  }, [isOpen, settings.username]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (file.type === 'application/json' || file.name.endsWith('.json')) {
        setSelectedFile(file);
        setError(null);
      } else {
        setError('请选择 .json 格式的文件');
      }
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.type === 'application/json' || file.name.endsWith('.json')) {
        setSelectedFile(file);
        setError(null);
      } else {
        setError('请选择 .json 格式的文件');
      }
    }
  }, []);

  const handleRemoveFile = useCallback(() => {
    setSelectedFile(null);
    setError(null);
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('请先选择文件');
      return;
    }

    if (!username || !username.trim()) {
      setError('请输入用户名');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const trimmedUsername = username.trim();
      console.log('[DEBUG] 准备发送的username值:', trimmedUsername);
      console.log('[DEBUG] selectedFile:', selectedFile.name, selectedFile.size);
      
      const result = await uploadDoubanFile(selectedFile, trimmedUsername);
      
      updateSettings({ username: trimmedUsername }, true);
      
      toast({
        type: 'success',
        message: `导入成功！共更新 ${result.import_count || 0} 条目`
      });
      
      setTimeout(() => {
        onClose();
        onSuccess();
      }, 1500);
    } catch (err) {
      console.error('豆瓣导入失败，完整错误对象:', err);
      
      let errorMessage = '上传失败，请重试';
      
      if (err instanceof Error) {
        if (err.message.includes('422')) {
          errorMessage = '上传失败: 请求参数错误';
        } else if (err.message.includes('404')) {
          errorMessage = '上传失败: 用户不存在';
        } else if (err.message.includes('400')) {
          errorMessage = `上传失败: ${err.message}`;
        } else if (err.message.includes('500')) {
          errorMessage = '上传失败: 服务器内部错误';
        } else {
          errorMessage = `上传失败: ${err.message}`;
        }
      }
      
      setError(errorMessage);
      toast({
        type: 'error',
        message: errorMessage
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <>
      <Dialog isOpen={isOpen} onClose={onClose} title="导入豆瓣数据">
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            请上传豆瓣导出工具生成的 JSON 文件
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Bangumi 用户名 / 系统用户名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-gray-800 dark:text-white"
              disabled={isUploading}
            />
          </div>

          <div
            className={`
              relative border-2 border-dashed rounded-lg p-8 text-center transition-all duration-200
              ${isDragging 
                ? 'border-primary bg-primary/5' 
                : 'border-gray-300 dark:border-gray-600 hover:border-primary/50'
              }
            `}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept=".json,application/json"
              onChange={handleFileSelect}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              disabled={isUploading}
            />
            
            {!selectedFile ? (
              <div className="space-y-2">
                <UploadCloud className="w-12 h-12 mx-auto text-gray-400" />
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  点击选择文件或拖拽文件到此处
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-500">
                  仅支持 .json 格式
                </p>
              </div>
            ) : (
              <div className="flex items-center justify-center gap-3">
                <FileText className="w-8 h-8 text-primary" />
                <div className="flex-1 text-left">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {(selectedFile.size / 1024).toFixed(2)} KB
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemoveFile();
                  }}
                  className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
                  disabled={isUploading}
                >
                  <X className="w-4 h-4 text-gray-500" />
                </button>
              </div>
            )}
          </div>

          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={isUploading}
              className="flex-1"
            >
              取消
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!selectedFile || isUploading}
              className="flex-1 flex items-center justify-center gap-2"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  上传中...
                </>
              ) : (
                '确认导入'
              )}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
