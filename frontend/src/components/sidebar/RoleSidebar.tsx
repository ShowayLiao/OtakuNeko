import React, { useState } from 'react';
import { Sparkles, UserCircle, Plus } from 'lucide-react';
import { DraggablePanel, Flexbox, ActionIcon, List, Avatar } from '@lobehub/ui';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { useRoleStore } from '@/store/useRoleStore';
import { useHasHydrated } from '@/store/useHasHydrated';
import PRESET_ROLES from '@/store/presetRoles';
import { Role } from '@/store/models';

interface RoleSidebarProps {
  activeRoleId: string;
  onRoleSelect: (roleId: string) => void;
}

export const RoleSidebar: React.FC<RoleSidebarProps> = ({ activeRoleId, onRoleSelect }) => {
  const [expand, setExpand] = useState(true);
  const hasHydrated = useHasHydrated();
  const { customRoles, addCustomRole } = useRoleStore();

  // 新增：创建角色的处理函数
  const handleCreateRole = () => {
    const newId = `custom-${Date.now()}`;
    const newRole: Role = {
      id: newId,
      name: '未命名角色',
      avatar: '🤖', // 给个默认头像
      description: '点击右侧编辑角色的描述信息...',
      promptConfig: {
        persona: '',
        tone: '',
        rules: ''
      },
      temperature: 0.6,
      isPreset: false,
    };
    
    // 1. 存入 Zustand (自动持久化)
    addCustomRole(newRole);
    // 2. 将右侧视图立即切换到刚创建的角色
    onRoleSelect(newId);
  };

  // 创建官方预设角色的items
  const presetItems = PRESET_ROLES.filter(r => r.isPreset).map(role => ({
    key: role.id,
    avatar: <Avatar avatar={role.avatar} shape="square" size={40} />,
    title: <span className="font-medium">{role.name}</span>,
    description: role.description,
  }));

  // 创建自定义角色的items
  const customItems = customRoles.map(role => ({
    key: role.id,
    avatar: <Avatar avatar={role.avatar} shape="square" size={40} />,
    title: <span className="font-medium">{role.name}</span>,
    description: role.description,
  }));

  return (
    <DraggablePanel
      expand={expand}
      mode="fixed"
      placement="left"
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: 300,
        backgroundColor: 'var(--lobe-color-bg-container)',
        backdropFilter: 'blur(16px)',
        borderRight: '1px solid var(--lobe-color-border)',
      }}
      onExpandChange={setExpand}
    >
      <Flexbox height="100%" width="100%" style={{ overflow: 'hidden' }}>
        
        {/* 优化的 Header 区：使用 ActionIcon，更现代的排版，增加底边距分割 */}
        <Flexbox 
          padding="16px" 
          horizontal 
          justify="space-between" 
          align="center"
          style={{ borderBottom: '1px solid var(--lobe-color-border-secondary)' }}
        >
          <span 
            className="font-bold text-base" 
            style={{ color: 'var(--lobe-color-text)' }}
          >
            角色列表
          </span>
          <ActionIcon 
            icon={Plus} 
            title="新建自定义角色" 
            size="small" 
            onClick={handleCreateRole}
          />
        </Flexbox>

        <Flexbox flex={1} padding="16px 12px" gap={24} style={{ overflowY: 'auto' }}>
          
          <div className="flex flex-col gap-1.5">
            <div 
              className="text-xs font-semibold mb-2 px-3 flex items-center gap-1.5"
              style={{ color: 'var(--lobe-color-text-description)' }}
            >
              <Sparkles size={14} />
              官方预设
            </div>
            <List 
              activeKey={activeRoleId} 
              items={presetItems} 
              onClick={({ key }) => onRoleSelect(key)} 
              style={{ borderRadius: 12 }}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <div 
              className="text-xs font-semibold mb-2 px-3 flex items-center gap-1.5"
              style={{ color: 'var(--lobe-color-text-description)' }}
            >
              <UserCircle size={14} />
              我的自定义
            </div>
            {!hasHydrated ? (
              <div 
                className="text-xs px-3 py-6 text-center border border-dashed rounded-xl m-1"
                style={{ 
                  color: 'var(--lobe-color-text-description)',
                  borderColor: 'var(--lobe-color-border-secondary)',
                  backgroundColor: 'var(--lobe-color-fill-quaternary)' 
                }}
              >
                加载中...
              </div>
            ) : customItems.length === 0 ? (
              <div 
                className="text-xs px-3 py-6 text-center border border-dashed rounded-xl m-1"
                style={{ 
                  color: 'var(--lobe-color-text-description)',
                  borderColor: 'var(--lobe-color-border-secondary)',
                  backgroundColor: 'var(--lobe-color-fill-quaternary)' 
                }}
              >
                暂无自定义角色
              </div>
            ) : (
              <List 
                activeKey={activeRoleId} 
                items={customItems} 
                onClick={({ key }) => onRoleSelect(key)} 
                style={{ borderRadius: 12 }}
              />
            )}
          </div>

        </Flexbox>
      </Flexbox>
    </DraggablePanel>
  );
};

export default RoleSidebar;