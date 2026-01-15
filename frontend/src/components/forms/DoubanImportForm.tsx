"use client";

import { useState, useCallback, useRef } from 'react';
import { UploadCloud, File, Loader2, Check, X } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { uploadDoubanFile } from '@/lib/api';

interface DoubanImportFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function DoubanImportForm({ isOpen, onClose, onSuccess }: DoubanImportFormProps) {
  const { toast } = useToast();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [importResult, setImportResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 处理文件选择
  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      // 检查文件类型
      if (file.type !== 'application/json') {
        toast({
          type: 'error',
          message: '请选择JSON格式的文件'
        });
        return;
      }
      
      // 检查文件大小（限制为10MB）
      if (file.size > 10 * 1024 * 1024) {
        toast({
          type: 'error',
          message: '文件大小不能超过10MB'
        });
        return;
      }
      
      setSelectedFile(file);
      setImportResult(null);
    }
  }, [toast]);

  // 触发文件选择
  const triggerFileSelect = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // 处理上传
  const handleUpload = useCallback(async () => {
    if (!selectedFile) {
      toast({
        type: 'info',
        message: '请先选择文件'
      });
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    
    // 模拟进度更新
    const progressInterval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + 10;
      });
    }, 300);

    try {
      const result = await uploadDoubanFile(selectedFile);
      setImportResult(result);
      setUploadProgress(100);
      
      toast({
        type: 'success',
        message: `成功导入 ${result.sync_count} 条收藏`
      });
      
      onSuccess?.();
      
      // 3秒后关闭
      setTimeout(() => {
        onClose();
      }, 3000);
    } catch (error) {
      console.error('Error importing Douban collection:', error);
      toast({
        type: 'error',
        message: '导入失败，请检查文件格式后重试'
      });
    } finally {
      clearInterval(progressInterval);
      setIsUploading(false);
    }
  }, [selectedFile, toast, onSuccess, onClose]);

  // 重置表单
  const handleReset = useCallback(() => {
    setSelectedFile(null);
    setUploadProgress(0);
    setImportResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="导入豆瓣收藏">
      <div className="space-y-4">
        {/* 文件选择区域 */}
        <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center">
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleFileSelect}
            className="hidden"
            aria-hidden="true"
          />
          
          <Button
            variant="outline"
            onClick={triggerFileSelect}
            disabled={isUploading}
            className="mb-4"
          >
            <UploadCloud className="w-4 h-4 mr-2" />
            选择文件
          </Button>
          
          <p className="text-sm text-gray-500 dark:text-gray-400">
            支持JSON格式文件，大小不超过10MB
          </p>
          
          {selectedFile && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <File className="w-4 h-4 text-primary" />
              <span className="text-sm font-medium">
                {selectedFile.name}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  handleReset();
                }}
                disabled={isUploading}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          )}
        </div>

        {/* 上传进度 */}
        {isUploading && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>上传中...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
              <div 
                className="bg-primary h-2.5 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* 导入结果 */}
        {importResult && (
          <div className="p-4 border rounded-lg bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
            <div className="flex items-center gap-2 mb-2">
              <Check className="w-5 h-5 text-green-600 dark:text-green-400" />
              <h4 className="font-medium text-green-800 dark:text-green-400">导入成功</h4>
            </div>
            <ul className="text-sm space-y-1 text-green-700 dark:text-green-300">
              <li>用户名: {importResult.username}</li>
              <li>导入数量: {importResult.sync_count} 条</li>
              <li>数据源: {importResult.source}</li>
              {importResult.subject_type && (
                <li>条目类型: {importResult.subject_type}</li>
              )}
            </ul>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isUploading}
          >
            取消
          </Button>
          <Button
            onClick={handleUpload}
            disabled={isUploading || !selectedFile}
          >
            {isUploading ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <UploadCloud className="w-4 h-4 mr-2" />
            )}
            导入
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
