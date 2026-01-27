'use client';

import { useState } from 'react';
import { Popover, Flexbox } from '@lobehub/ui';
import { Palette, ChevronDown, Check } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { PrimaryColors } from '@lobehub/ui';

// 1. 官方标准色 (传 Key)
const STANDARD_MAP = {
  purple: '#BD54C6',
  green: '#78B885',
  orange: '#F1AD63',
  gold: '#EAB85E',
  red: '#F4416C',
  magenta: '#E34BA9',
  volcano: '#EC5E41',
  geekblue: '#0072F5',
};

// 2. 二次元色 (传 Hex)
const ANIME_MAP = {
  sakura: '#ffc0cb', // 樱花
};

// 3. 颜色文字映射表
const COLOR_TEXT_MAP: { [key: string]: string } = {
  // 官方标准色
  purple: '初号机',
  green: '扎古绿',
  orange: '小埋橙',
  gold: '宫园薰金',
  red: '助手红',
  magenta: '小圆粉',
  volcano: '明日香红',
  geekblue: '蕾姆蓝',
  // 二次元色
  sakura: '樱花粉',
};

export const ThemeSwitcher = () => {
  const { primaryColor, setPrimaryColor } = useAppTheme();
  const [open, setOpen] = useState(false);

  // 辅助函数：显示当前颜色（如果是名字，查表；如果是Hex，直接用）
  // 注意：这里要做一个类型断言，因为 primaryColor 可能是 hex 字符串
  const displayColor = STANDARD_MAP[primaryColor as keyof typeof STANDARD_MAP] || primaryColor;

  // 首字母大写
  const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

  // 渲染列表函数
  const renderList = (map: Record<string, string>, isStandard: boolean) => (
    Object.entries(map).map(([key, hex]) => {
      // 选中判断：官方色比对 Key，自定义色比对 Hex
      const isActive = isStandard ? primaryColor === key : primaryColor === hex;
      
      return (
        <Flexbox
          key={key}
          horizontal
          align="center"
          gap={12}
          onClick={() => {
            // 核心点击逻辑：官方色传 Key，自定义色传 Hex
            setPrimaryColor(isStandard ? key : hex);
            setOpen(false);
          }}
          style={{
            padding: '8px 12px',
            cursor: 'pointer',
            borderRadius: 8,
            background: isActive ? 'var(--lobe-color-fill-secondary)' : 'transparent',
            transition: 'all 0.2s',
          }}
          className="hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: hex,
              boxShadow: '0 0 0 1px rgba(0,0,0,0.1)',
            }}
          />
          <span style={{ fontSize: 14, flex: 1 }}>
            {/* 使用文字映射，默认使用首字母大写的 key */}
            {COLOR_TEXT_MAP[key] || capitalize(key)}
          </span>
          {isActive && <Check size={14} style={{ opacity: 0.6 }} />}
        </Flexbox>
      );
    })
  );

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="rightBottom"
      arrow={false}
      content={
        <Flexbox
          padding={8}
          gap={4}
          width={220}
          style={{ maxHeight: 400, overflowY: 'auto' }}
        >
          <div 
            style={{ 
              color: 'var(--lobe-color-text-3)', 
              fontSize: 11, 
              fontWeight: 600, 
              padding: '4px 12px', 
              textTransform: 'uppercase', 
              marginBottom: 2,
            }} 
          >
            预设颜色
          </div>
          {renderList(STANDARD_MAP, true)}

          <div 
            style={{ 
              color: 'var(--lobe-color-text-3)', 
              fontSize: 11, 
              fontWeight: 600, 
              padding: '4px 12px', 
              textTransform: 'uppercase', 
              marginBottom: 2,
              marginTop: 8,
            }} 
          >
            自定义颜色
          </div>
          {renderList(ANIME_MAP, false)}
        </Flexbox>
      }
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: 8,
          cursor: 'pointer',
          borderRadius: 6,
          transition: 'all 0.2s',
          background: open ? 'var(--lobe-color-fill-tertiary)' : 'transparent',
        }}
        className="hover:bg-neutral-100 dark:hover:bg-neutral-800"
      >
        <Palette size={30} strokeWidth={1.5} color={displayColor} />
      </div>
    </Popover>
  );
};