import React from 'react';
import { Select, Avatar } from '@lobehub/ui';
import { useRoleStore } from '@/store/useRoleStore';
import presetRoles from '@/store/presetRoles';

interface RoleSelectorProps {
  value: string; // 当前选中的角色ID
  onChange: (roleId: string) => void; // 回调：返回角色ID
}

export const RoleSelector = ({ value, onChange }: RoleSelectorProps) => {
  // 从 Store 获取所有自定义角色
  const customRoles = useRoleStore((s) => s.customRoles);

  // 合并预设角色和自定义角色
  const allRoles = [...presetRoles, ...customRoles];

  // 计算可用角色列表
  const availableOptions = allRoles.map((role) => ({
    label: (
      <div className="flex items-center gap-2 min-w-0">
        <Avatar avatar={role.avatar} size={16} shape="square" />
        <span className="flex-1 min-w-0 truncate">{role.name}</span>
        {role.isPreset && (
          <span className="text-xs text-gray-400 ml-2 whitespace-nowrap">预设</span>
        )}
      </div>
    ),
    value: role.id,
  }));

  return (
    <Select
      value={value}
      options={availableOptions}
      onChange={onChange}
      // 样式微调，让它看起来像个胶囊
      variant="borderless" 
      style={{ width: 180 }}
      className="truncate hover:bg-gray-50"
    />
  );
};
