"use client";

import React, { useState } from 'react';
import { Button, Popover, message } from 'antd';
import { Bot, Import, Download, MoreHorizontal, ChevronDown, Database } from 'lucide-react';
import { Flexbox } from '@lobehub/ui';
import { Header } from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { useRoleStore } from '@/store/useRoleStore';
import RoleImportModal from '@/components/Modal/RoleImportModal';

export default function PersonaHeader() {
  const { isDarkMode, primaryColor } = useAppTheme();
  const { exportRoles, importRoles } = useRoleStore();
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);

  // 处理导入事件
  const handleImport = () => {
    setIsImportModalOpen(true);
  };

  // 处理导出事件
  const handleExport = () => {
    exportRoles();
    message.success('角色配置已导出');
  };

  // 处理导入完成事件
  const handleImportComplete = (roles: any) => {
    importRoles(roles);
    message.success('角色配置已导入');
  };

  // Header 左侧组合内容
  const HeaderLeftContent = (
    <div className="flex items-center gap-1 -ml-2">
      <div className="flex items-center gap-3 px-2">
        <Bot size={20} style={{ color: primaryColor }} />
        <span className="text-xl font-bold font-sans tracking-tight" style={{ color: primaryColor }}>
          角色工作室
        </span>
      </div>
    </div>
  );

  // Header 中间组合内容
  const HeaderCenterContent = (
    <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '16px' }}>
      <Popover 
        placement="bottomLeft" 
        trigger="click" 
        arrow={false}
        content={
          <Flexbox gap={6} style={{ minWidth: 160, padding: '8px' }}>
            <div
              style={{
                color: 'var(--lobe-color-text-3)',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.5px',
                padding: '4px 8px',
                textTransform: 'uppercase',
              }}
            >
              数据管理
            </div>
            <Flexbox
              horizontal
              align="center"
              style={{
                borderRadius: 8,
                cursor: 'pointer',
                padding: '8px 12px',
                transition: 'all 0.2s',
              }}
              className="hover:bg-gray-100 dark:hover:bg-gray-800"
              onClick={handleImport}
            >
              <Import size={16} style={{ marginRight: 10 }} />
              <span style={{ flex: 1, fontSize: 14 }}>导入本地配置</span>
            </Flexbox>
            <Flexbox
              horizontal
              align="center"
              style={{
                borderRadius: 8,
                cursor: 'pointer',
                padding: '8px 12px',
                transition: 'all 0.2s',
              }}
              className="hover:bg-gray-100 dark:hover:bg-gray-800"
              onClick={handleExport}
            >
              <Download size={16} style={{ marginRight: 10 }} />
              <span style={{ flex: 1, fontSize: 14 }}>导出为 JSON</span>
            </Flexbox>
          </Flexbox>
        } 
      >
        <Button 
          icon={<Database size={16} />} 
          style={{ gap: 6 }} 
          type="text"
        >
          导入与导出
          <ChevronDown size={14} style={{ opacity: 0.6 }} />
        </Button>
      </Popover>
    </div>
  );

  return (
    <div className={`w-full ${isDarkMode ? 'dark:bg-gray-800 border-b border-gray-800' : 'bg-white border-b border-gray-100'} z-10`}>
      <Header leftArea={HeaderLeftContent} centerArea={HeaderCenterContent} />
      <RoleImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImport={handleImportComplete}
      />
    </div>
  );
}