import React, { useState, useRef } from 'react';
import { Modal, Button, Alert } from 'antd';
import { Upload, CloudUpload, FileText } from 'lucide-react';
import { Flexbox } from '@lobehub/ui';

interface RoleImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (roles: any) => void;
}

export default function RoleImportModal({ isOpen, onClose, onImport }: RoleImportModalProps) {
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      handleFile(file);
    }
  };

  const handleFile = (file: File) => {
    setFileError(null);
    
    if (file.type !== 'application/json') {
      setFileError('请选择JSON格式的文件');
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const roles = JSON.parse(content);
        onImport(roles);
        onClose();
      } catch (error) {
        setFileError('JSON文件格式错误');
      }
    };
    reader.onerror = () => {
      setFileError('文件读取失败');
    };
    reader.readAsText(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => {
    setDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFile(file);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <Modal
      title="导入角色配置"
      open={isOpen}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
      ]}
      width={500}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />
      
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${dragging ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-300 dark:border-gray-700'}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <Flexbox direction="column" align="center" gap={4}>
          <CloudUpload size={48} className="text-gray-400" />
          <div>
            <p className="text-lg font-medium">点击或拖拽文件到此处</p>
            <p className="text-sm text-gray-500 mt-2">支持 .json 格式文件</p>
          </div>
        </Flexbox>
      </div>

      {fileError && (
        <Alert
          message="错误"
          description={fileError}
          type="error"
          showIcon
          className="mt-4"
        />
      )}

      <div className="mt-4 text-sm text-gray-500">
        <p>导入说明：</p>
        <ul className="list-disc pl-5 mt-2 space-y-1">
          <li>导入的文件必须是有效的JSON格式</li>
          <li>文件应包含角色配置数组</li>
          <li>导入将覆盖现有自定义角色</li>
        </ul>
      </div>
    </Modal>
  );
}
