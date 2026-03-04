'use client';

import React, { useState } from 'react';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { Input, Slider, Tag } from 'antd';
import { MessageSquare, Flame, Trash2 } from 'lucide-react';
import { Button, Popconfirm } from 'antd';
import EmojiPicker from 'emoji-picker-react';
import { Popover, Avatar } from '@lobehub/ui';
import PersonaHeader from '@/components/header/PersonaHeader';
import RoleSidebar from '@/components/sidebar/RoleSidebar';
import { Role } from '@/store/models';
import PRESET_ROLES from '@/store/presetRoles';
import { useRoleStore } from '@/store/useRoleStore';

const { TextArea } = Input;

export default function PersonaDetailPage() {
  const { isDarkMode } = useAppTheme();
  const { customRoles, updateCustomRole, removeCustomRole } = useRoleStore();
  
  // 页面状态
  const [activeRoleId, setActiveRoleId] = useState<string>('preset-2');
  
  // 合并预设角色和自定义角色
  const allRoles = [...PRESET_ROLES, ...customRoles];
  
  // 获取当前选中的角色
  const activeRole = allRoles.find(r => r.id === activeRoleId) || allRoles[0] || {
    id: 'default',
    name: '默认角色',
    avatar: '🤖',
    description: '默认角色',
    promptConfig: {
      persona: '',
      tone: '',
      rules: ''
    },
    temperature: 0.6,
    isPreset: true
  };
  
  // 更新当前角色的属性
  const updateActiveRole = (updates: Partial<Role>) => {
    if (activeRole.isPreset) return; // 预设角色禁止修改
    
    // 更新store中的自定义角色
    updateCustomRole(activeRoleId, updates);
  };

  // 新增：删除处理逻辑
  const handleDeleteRole = () => {
    removeCustomRole(activeRoleId);
    // 删除后，自动选中列表里的第一个角色（通常是预设角色）
    setActiveRoleId(allRoles[0]?.id || '');
  };

  // 新增：更新promptConfig的辅助函数
  const updatePromptConfig = (key: keyof typeof activeRole.promptConfig, value: string) => {
    if (activeRole.isPreset) return;
    updateCustomRole(activeRoleId, {
      promptConfig: { ...activeRole.promptConfig, [key]: value }
    });
  };

  return (
    <div className={`flex flex-col h-full overflow-hidden ${isDarkMode ? 'dark:bg-neutral-950' : 'bg-white'}`}>
      {/* 顶部 Header：固定在顶部 */}
      <div className="flex-none z-10">
        <PersonaHeader />
      </div>

      {/* 核心内容区 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧可拖拽面板 */}
        <RoleSidebar 
          activeRoleId={activeRoleId}
          onRoleSelect={setActiveRoleId}
        />
        
        {/* 右侧内容区域 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 滚动区域 */}
          <div className="flex-1 overflow-y-auto bg-transparent">
            <div className="max-w-3xl mx-auto px-8 py-12 flex flex-col gap-10">
              
              {/* 1. 顶部角色基础信息 */}
              <div className="flex gap-6 items-start">
                {/* 头像 */}
                <div className="flex flex-col items-center gap-2 flex-shrink-0">
                  <Popover 
                    content={<EmojiPicker onEmojiClick={(e) => updateActiveRole({ avatar: e.emoji })} />} 
                    trigger="click" 
                    disabled={activeRole.isPreset} 
                  >
                    <div className="cursor-pointer relative group">
                      <Avatar avatar={activeRole.avatar} shape="square" size={96} />
                      {!activeRole.isPreset && (
                        <div className="absolute inset-0 bg-black/20 rounded-2xl flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                          <span className="text-white text-sm font-medium">点击修改</span>
                        </div>
                      )}
                    </div>
                  </Popover>
                </div>
                
                {/* 标题与描述 */}
                <div className="flex flex-col gap-3 pt-2 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <Input 
                        value={activeRole.name} 
                        onChange={e => updateActiveRole({ name: e.target.value })}
                        disabled={activeRole.isPreset}
                        variant="borderless"
                        className="text-xl font-semibold p-0 text-gray-800 dark:text-gray-100 placeholder-gray-300 h-auto w-auto"
                      />
                      {activeRole.isPreset ? (
                        <Tag 
                          color="blue" 
                          bordered={false} 
                          className="m-0 rounded text-xs px-2 py-0.5 bg-blue-50 text-blue-500 dark:bg-blue-900/30 dark:text-blue-400"
                        >
                          官方预设
                        </Tag>
                      ) : (
                        <Tag 
                          color="green" 
                          bordered={false} 
                          className="m-0 rounded text-xs px-2 py-0.5"
                        >
                          自定义
                        </Tag>
                      )}
                    </div>

                    {/* 新增：如果是自定义角色，显示删除按钮 */}
                    {!activeRole.isPreset && (
                      <Popconfirm
                        title="确定要删除这个角色吗？"
                        description="删除后将无法恢复。"
                        onConfirm={handleDeleteRole}
                        okText="确认删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                      >
                        <Button
                          type="text"
                          danger
                          icon={<Trash2 size={16} />}
                          className="text-gray-400 hover:text-red-500"
                        >
                          删除角色
                        </Button>
                      </Popconfirm>
                    )}
                  </div>
                  <Input 
                    value={activeRole.description} 
                    onChange={e => updateActiveRole({ description: e.target.value })}
                    disabled={activeRole.isPreset}
                    variant="borderless"
                    placeholder="用一句话描述这个角色..."
                    className="text-gray-400 dark:text-gray-500 p-0 text-sm"
                  />
                </div>
              </div>

              {/* 分割线 */}
              <div className="h-px w-full bg-gray-100 dark:bg-gray-800/60"></div>

              {/* 2. 核心指令 (Prompt Config) */}
              <div className="flex flex-col gap-6">
                <div className="flex items-center gap-2 text-lg font-bold text-gray-800 dark:text-gray-200">
                  <MessageSquare className="text-blue-500 w-5 h-5" /> 
                  核心指令
                </div>
                <div className="text-sm text-gray-400">
                  这是注入给 AI 的“灵魂”，它将严格按照此处的规则与你对话。
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* 核心身份 */}
                  <div className={`p-5 rounded-2xl border ${activeRole.isPreset ? 'bg-gray-50/50 dark:bg-[#141414] border-gray-200 dark:border-gray-800' : 'bg-white dark:bg-[#1a1a1a] border-gray-100 dark:border-gray-700 shadow-sm'}`}>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">核心身份</label>
                    <Input
                      value={activeRole.promptConfig?.persona || ''}
                      onChange={e => updatePromptConfig('persona', e.target.value)}
                      disabled={activeRole.isPreset}
                      placeholder="如：你是一个资深的动画评论家"
                      className="w-full"
                    />
                  </div>
                  
                  {/* 语气风格 */}
                  <div className={`p-5 rounded-2xl border ${activeRole.isPreset ? 'bg-gray-50/50 dark:bg-[#141414] border-gray-200 dark:border-gray-800' : 'bg-white dark:bg-[#1a1a1a] border-gray-100 dark:border-gray-700 shadow-sm'}`}>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">语气风格</label>
                    <Input
                      value={activeRole.promptConfig?.tone || ''}
                      onChange={e => updatePromptConfig('tone', e.target.value)}
                      disabled={activeRole.isPreset}
                      placeholder="如：充满颜艺、大量使用感叹号、傲娇"
                      className="w-full"
                    />
                  </div>
                  
                  {/* 行为准则 */}
                  <div className={`p-5 rounded-2xl border ${activeRole.isPreset ? 'bg-gray-50/50 dark:bg-[#141414] border-gray-200 dark:border-gray-800' : 'bg-white dark:bg-[#1a1a1a] border-gray-100 dark:border-gray-700 shadow-sm'}`}>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">行为准则</label>
                    <TextArea
                      rows={3}
                      value={activeRole.promptConfig?.rules || ''}
                      onChange={e => updatePromptConfig('rules', e.target.value)}
                      disabled={activeRole.isPreset}
                      placeholder="如：不要剧透、必须用JSON格式返回等"
                      className="w-full"
                    />
                  </div>
                </div>
              </div>

              {/* 3. 模型发散度 (Temperature) 卡片 */}
              <div className="flex flex-col gap-6 bg-white dark:bg-[#141414] border border-gray-100 dark:border-gray-800 p-6 rounded-2xl shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-base font-bold text-gray-800 dark:text-gray-200">
                    <Flame className="text-orange-500 w-5 h-5" /> 
                    模型发散度 (Temperature)
                  </div>
                  <div className="text-sm font-mono bg-gray-50 dark:bg-gray-800 px-3 py-1 rounded-md text-gray-600 dark:text-gray-300 border border-gray-100 dark:border-gray-700">
                    {activeRole.temperature}
                  </div>
                </div>
                
                <div className="flex items-center gap-6 px-2">
                  <span className="text-sm text-gray-400 whitespace-nowrap">严谨写实</span>
                  <Slider 
                    min={0} 
                    max={2} 
                    step={0.1} 
                    value={activeRole.temperature} 
                    onChange={v => updateActiveRole({ temperature: v })}
                    disabled={activeRole.isPreset}
                    className="flex-1 m-0"
                    tooltip={{ open: false }}
                  />
                  <span className="text-sm text-gray-400 whitespace-nowrap">脑洞大开</span>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}