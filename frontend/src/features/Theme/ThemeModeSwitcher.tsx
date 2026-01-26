'use client';

import { useState } from 'react';
import { Popover, Flexbox } from '@lobehub/ui';
import { Monitor, Moon, Sun, Check } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';

export const ThemeModeSwitcher = () => {
  // 注意：这里我们解构的是 appearance 和 setAppearance
  const { appearance, setAppearance, isDarkMode } = useAppTheme();
  const [open, setOpen] = useState(false);

  const items = [
    { key: 'auto', label: '跟随系统', icon: Monitor },
    { key: 'light', label: '亮色模式', icon: Sun },
    { key: 'dark',  label: '暗色模式', icon: Moon },
  ];

  // 图标显示逻辑：如果是自动，显示显示器图标；否则显示月亮/太阳
  // 或者你也可以希望 icon 始终反映当前的视觉效果，那就用 isDarkMode ? Moon : Sun
  const CurrentIcon = isDarkMode ? Moon : Sun;

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottom" // 建议改为 bottom，放在 header 里更自然
      arrow={false}
      content={
        <Flexbox padding={4} width={160}>
          {items.map((item) => {
            // 核心修复：判断 isActive 使用的是 appearance 状态 (auto/light/dark)
            const isActive = appearance === item.key;
            
            return (
              <Flexbox
                key={item.key}
                horizontal
                align="center"
                gap={8}
                onClick={() => {
                  // 核心修复：直接设置偏好，不需要手动计算系统主题
                  setAppearance(item.key as 'auto' | 'light' | 'dark');
                  setOpen(false);
                }}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  borderRadius: 6,
                  color: isActive ? 'var(--lobe-color-primary)' : 'inherit',
                  background: isActive ? 'var(--lobe-color-fill-secondary)' : 'transparent',
                }}
                className="hover:bg-neutral-100 dark:hover:bg-neutral-800"
              >
                <item.icon size={16} />
                <span style={{ fontSize: 14 }}>{item.label}</span>
                {isActive && <Check size={14} style={{ marginLeft: 'auto' }} />}
              </Flexbox>
            );
          })}
        </Flexbox>
      }
    >
      <div 
        className="hover:bg-neutral-100 dark:hover:bg-neutral-800"
        style={{
          padding: 8,
          borderRadius: 6,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.2s',
          // 只有打开菜单时才显示背景色
          background: open ? 'var(--lobe-color-fill-tertiary)' : 'transparent',
        }}
      >
        <CurrentIcon size={20} style={{ opacity: 0.8 }} />
      </div>
    </Popover>
  );
};