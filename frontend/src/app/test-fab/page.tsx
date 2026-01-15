"use client";

import { useState } from 'react';
import { FloatingActionButton } from '@/components/features/FloatingActionButton';
import { SubjectSearchForm } from '@/components/forms/SubjectSearchForm';
import { DoubanImportForm } from '@/components/forms/DoubanImportForm';
import { CollectionEditForm } from '@/components/forms/CollectionEditForm';

export default function TestFABPage() {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  // 处理操作成功
  const handleActionSuccess = (actionType: string, data?: any) => {
    console.log(`Action ${actionType} succeeded`, data);
    // 可以在这里添加刷新数据等操作
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-4xl mx-auto p-8">
        <h1 className="text-3xl font-bold mb-8">FloatingActionButton 测试页面</h1>
        
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">功能说明</h2>
          <ul className="space-y-2">
            <li>点击右下角的浮动按钮展开操作菜单</li>
            <li>"添加收藏" - 搜索并添加新的收藏</li>
            <li>"导入豆瓣收藏" - 上传豆瓣数据文件导入收藏</li>
            <li>"修改收藏" - 查看和修改已有的收藏</li>
          </ul>
        </div>
        
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold mb-4">测试区域</h2>
          <p className="text-gray-600 dark:text-gray-300">
            这个页面用于测试 FloatingActionButton 组件的功能。
            请尝试使用不同的操作，查看是否能正常工作。
          </p>
        </div>
      </div>
      
      {/* FloatingActionButton 组件 */}
      <FloatingActionButton
        onActionSuccess={(actionType, data) => {
          handleActionSuccess(actionType, data);
          if (actionType === 'add') {
            setIsAddModalOpen(true);
          } else if (actionType === 'import') {
            setIsImportModalOpen(true);
          } else if (actionType === 'edit') {
            setIsEditModalOpen(true);
          }
        }}
      />
      
      {/* 添加收藏模态框 */}
      <SubjectSearchForm
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onSuccess={() => handleActionSuccess('add-success')}
      />
      
      {/* 导入豆瓣收藏模态框 */}
      <DoubanImportForm
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onSuccess={() => handleActionSuccess('import-success')}
      />
      
      {/* 修改收藏模态框 */}
      <CollectionEditForm
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        onSuccess={() => handleActionSuccess('edit-success')}
      />
    </div>
  );
}
