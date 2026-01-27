"use client";
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import { MessageSquare, Grid, Wrench, UserCircle, Settings } from 'lucide-react';
import { Avatar, DraggableSideNav, ActionIcon, Flexbox, Menu, Text, type MenuItemType } from '@lobehub/ui';
import { theme } from 'antd';
import { ThemeSwitcher } from '@/features/Theme/ThemeSwitcher';
import { ThemeModeSwitcher } from '@/features/Theme/ThemeModeSwitcher';

export const DesktopSidebar = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { token } = theme.useToken();
  const [width, setWidth] = useState(280);
  const [expand, setExpand] = useState(true);
  const [activeKey, setActiveKey] = useState<string>(pathname || '');
  
  // 主导航项
  const mainItems: MenuItemType[] = [
    { key: '/', icon: <MessageSquare strokeWidth={1.5} />, label: '聊天' },
    { key: '/collections', icon: <Grid strokeWidth={1.5} />, label: '收藏' },
    { key: '/tools', icon: <Wrench strokeWidth={1.5} />, label: '工具' },
    { key: '/role', icon: <UserCircle strokeWidth={1.5} />, label: '角色' },
    { key: '/settings', icon: <Settings strokeWidth={1.5} />, label: '设置' },
  ];

  const handleSelect = (key: string) => {
    setActiveKey(key);
    router.push(key);
  };
  
  return (
    <DraggableSideNav
      style={{
        background: token.colorBgContainer, // 之前改过的亮色背景

        // ✅ 行业推荐写法：保持 1px，但使用标准边框色 (更深)
        borderRight: `1px solid ${token.colorBorder}`, 
        
        height: '100vh'
      }}
      body={(isExpanded) => (
        <Flexbox style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          <Menu
            inlineCollapsed={!isExpanded}
            items={mainItems}
            mode={'inline'}
            onSelect={({ key }) => handleSelect(key)}
            selectable
            selectedKeys={[activeKey]}
            variant={'borderless'}
          />
        </Flexbox>
      )}
      expand={expand}
      footer={(isExpanded) => (
        <Flexbox
          align={'flex-start'}
          gap={8}
          direction={'vertical'}
          justify={'flex-start'}
          padding={4}
          style={{
            width: '100%',
          }}
        >
          <Flexbox
            align={'center'}
            gap={8}
            horizontal
            justify={'flex-start'}
            style={{
              width: '100%',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
            }}
          >
            <ThemeSwitcher />
            {isExpanded && (
              <span style={{ fontSize: 14, color: token.colorText, fontWeight: 500 }}>主题颜色</span>
            )}
          </Flexbox>
          <Flexbox
            align={'center'}
            gap={8}
            horizontal
            justify={'flex-start'}
            style={{
              width: '100%',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
            }}
          >
            <ThemeModeSwitcher />
            {isExpanded && (
              <span style={{ fontSize: 14, color: token.colorText, fontWeight: 500 }}>主题模式</span>
            )}
          </Flexbox>
        </Flexbox>
      )}
      header={(isExpanded) => (
        <Flexbox>
          <Flexbox
            align={'center'}
            gap={8}
            horizontal
            justify={'flex-start'}
            padding={4}
            style={{
              margin: 4,
            }}
          >
          </Flexbox>
        </Flexbox>
      )}
      minWidth={64}
      maxWidth={200}
      onExpandChange={setExpand}
      onWidthChange={(_, newWidth) => setWidth(newWidth)}
      placement="left"
      resizable={true}
      width={width}
    />
  );
};
