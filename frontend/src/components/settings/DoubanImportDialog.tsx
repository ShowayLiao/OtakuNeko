"use client";

import { useState, useCallback, useEffect, useRef } from 'react';
import { UploadCloud, FileText, X, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { uploadDoubanFile, login } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';
import { cn } from '@/lib/utils';

interface DoubanImportDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface ValidationError {
  username?: string;
  file?: string;
}

export function DoubanImportDialog({ isOpen, onClose, onSuccess }: DoubanImportDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState<string>('');
  const [validationErrors, setValidationErrors] = useState<ValidationError>({});
  const [isSuccess, setIsSuccess] = useState(false);
  const { toast } = useToast();
  const { settings, updateSettings } = useSettings();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const usernameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      if (settings.username) {
        setUsername(settings.username);
      } else {
        setUsername('');
      }
      setSelectedFile(null);
      setError(null);
      setValidationErrors({});
      setIsSuccess(false);
      setUploadProgress(0);
      
      setTimeout(() => {
        usernameInputRef.current?.focus();
      }, 100);
    }
  }, [isOpen, settings.username]);

  const validateUsername = useCallback((value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) {
      return '请输入用户名';
    }
    if (trimmed.length < 2) {
      return '用户名至少需要2个字符';
    }
    if (trimmed.length > 50) {
      return '用户名不能超过50个字符';
    }
    if (!/^[a-zA-Z0-9_\u4e00-\u9fa5-]+$/.test(trimmed)) {
      return '用户名只能包含字母、数字、下划线、连字符和中文';
    }
    return null;
  }, []);

  const validateFile = useCallback((file: File | null): string | null => {
    if (!file) {
      return '请选择文件';
    }
    if (!file.name.endsWith('.json') && file.type !== 'application/json') {
      return '请选择 .json 格式的文件';
    }
    if (file.size === 0) {
      return '文件不能为空';
    }
    if (file.size > 10 * 1024 * 1024) {
      return '文件大小不能超过10MB';
    }
    return null;
  }, []);

  const handleUsernameChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setUsername(value);
    const error = validateUsername(value);
    setValidationErrors(prev => ({ ...prev, username: error || undefined }));
    setError(null);
  }, [validateUsername]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      const error = validateFile(file);
      if (error) {
        setValidationErrors(prev => ({ ...prev, file: error }));
        setError(error);
      } else {
        setSelectedFile(file);
        setValidationErrors(prev => ({ ...prev, file: undefined }));
        setError(null);
      }
    }
  }, [validateFile]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const error = validateFile(file);
      if (error) {
        setValidationErrors(prev => ({ ...prev, file: error }));
        setError(error);
      } else {
        setSelectedFile(file);
        setValidationErrors(prev => ({ ...prev, file: undefined }));
        setError(null);
      }
    }
  }, [validateFile]);

  const handleRemoveFile = useCallback(() => {
    setSelectedFile(null);
    setValidationErrors(prev => ({ ...prev, file: undefined }));
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const handleUpload = async () => {
    const usernameError = validateUsername(username);
    const fileError = validateFile(selectedFile);
    
    if (usernameError || fileError) {
      setValidationErrors({
        username: usernameError || undefined,
        file: fileError || undefined
      });
      setError(usernameError || fileError || '请检查输入');
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setError(null);
    setIsSuccess(false);

    const progressInterval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + 10;
      });
    }, 200);

    try {
      const trimmedUsername = username.trim();
      
      if (!selectedFile) {
        throw new Error('请选择要上传的文件');
      }
      
      // 1. 首先确保用户已登录，获取JWT token
      await login(trimmedUsername);
      
      // 2. 上传豆瓣文件
      const result = await uploadDoubanFile(selectedFile);
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      setIsSuccess(true);
      
      updateSettings({ username: trimmedUsername }, true);
      
      toast({
        type: 'success',
        message: `导入成功！共更新 ${result.sync_count || 0} 条目`
      });
      
      setTimeout(() => {
        onClose();
        onSuccess();
      }, 1500);
    } catch (err) {
      clearInterval(progressInterval);
      setUploadProgress(0);
      setIsSuccess(false);
      
      console.error('豆瓣导入失败，完整错误对象:', err);
      
      let errorMessage = '上传失败，请重试';
      
      if (err instanceof Error) {
        if (err.message.includes('422')) {
          errorMessage = '上传失败: 请求参数错误，请检查文件格式';
        } else if (err.message.includes('404')) {
          errorMessage = '上传失败: 用户不存在，请确认用户名正确';
        } else if (err.message.includes('400')) {
          errorMessage = `上传失败: ${err.message}`;
        } else if (err.message.includes('500')) {
          errorMessage = '上传失败: 服务器内部错误，请稍后重试';
        } else if (err.message.includes('413')) {
          errorMessage = '上传失败: 文件过大，请确保文件小于10MB';
        } else if (err.message.includes('401')) {
          errorMessage = '上传失败: 认证失败，请重新登录';
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

  const isFormValid = !validationErrors.username && !validationErrors.file && selectedFile && username.trim().length > 0;

  return (
    <>
      <Dialog 
        isOpen={isOpen} 
        onClose={onClose} 
        title="导入豆瓣数据"
      >
        <div className="space-y-5">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            请上传豆瓣导出工具生成的 JSON 文件，系统将自动解析并导入您的收藏数据
          </p>

          <div>
            <label 
              htmlFor="username-input"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
            >
              Bangumi 用户名 / 系统用户名
              <span className="text-red-500 ml-1">*</span>
            </label>
            <input
              ref={usernameInputRef}
              id="username-input"
              type="text"
              value={username}
              onChange={handleUsernameChange}
              placeholder="请输入用户名"
              className={cn(
                "w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent dark:bg-gray-800 dark:text-white transition-colors",
                validationErrors.username 
                  ? "border-red-300 dark:border-red-600 focus:ring-red-500" 
                  : "border-gray-300 dark:border-gray-600"
              )}
              disabled={isUploading}
              aria-invalid={!!validationErrors.username}
              aria-describedby={validationErrors.username ? "username-error" : undefined}
            />
            {validationErrors.username && (
              <p 
                id="username-error"
                className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1"
              >
                <AlertCircle className="w-4 h-4" />
                {validationErrors.username}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              选择文件
              <span className="text-red-500 ml-1">*</span>
            </label>
            <div
              className={cn(
                "relative border-2 border-dashed rounded-lg p-8 text-center transition-all duration-200",
                isDragging 
                  ? 'border-primary bg-primary/5 scale-[1.02]' 
                  : 'border-gray-300 dark:border-gray-600 hover:border-primary/50',
                validationErrors.file && 'border-red-300 dark:border-red-600',
                isUploading && 'pointer-events-none opacity-60'
              )}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              role="button"
              tabIndex={0}
              aria-label="点击或拖拽文件到此处上传"
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,application/json"
                onChange={handleFileSelect}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                disabled={isUploading}
                aria-label="选择文件"
              />
              
              {!selectedFile ? (
                <div className="space-y-3">
                  <UploadCloud className={cn(
                    "w-12 h-12 mx-auto transition-colors",
                    isDragging ? 'text-primary' : 'text-gray-400'
                  )} />
                  <div>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      点击选择文件或拖拽文件到此处
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                      仅支持 .json 格式，最大 10MB
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center gap-3">
                  <FileText className="w-8 h-8 text-primary" />
                  <div className="flex-1 text-left min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {(selectedFile.size / 1024).toFixed(2)} KB
                    </p>
                  </div>
                  {!isUploading && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveFile();
                      }}
                      className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                      aria-label="移除文件"
                    >
                      <X className="w-4 h-4 text-gray-500" />
                    </button>
                  )}
                </div>
              )}
            </div>
            {validationErrors.file && (
              <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1">
                <AlertCircle className="w-4 h-4" />
                {validationErrors.file}
              </p>
            )}
          </div>

          {isUploading && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">上传进度</span>
                <span className="font-medium text-gray-900 dark:text-white">{uploadProgress}%</span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                <div 
                  className="bg-primary h-full transition-all duration-300 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                  role="progressbar"
                  aria-valuenow={uploadProgress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
            </div>
          )}

          {isSuccess && (
            <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
              <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
              <p className="text-sm text-green-700 dark:text-green-300">文件上传成功，正在处理数据...</p>
            </div>
          )}

          {error && !isUploading && (
            <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={isUploading}
              className="flex-1"
              type="button"
            >
              取消
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!isFormValid || isUploading}
              className="flex-1 flex items-center justify-center gap-2"
              type="button"
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
