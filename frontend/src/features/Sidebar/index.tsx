"use client";
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import { MessageSquare, Grid, Wrench, UserCircle, Settings } from 'lucide-react';
import { Avatar, DraggableSideNav, ActionIcon, Flexbox, Menu, Text, type MenuItemType } from '@lobehub/ui';
import { theme } from 'antd';

export const DesktopSidebar = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { token } = theme.useToken();
  const [width, setWidth] = useState(280);
  const [expand, setExpand] = useState(true);
  const [activeKey, setActiveKey] = useState<string>(pathname || '');
  
  // 主导航项
  const mainItems: MenuItemType[] = [
    { key: '/', icon: <MessageSquare className="h-5 w-5" />, label: 'Chat' },
    { key: '/collections', icon: <Grid className="h-5 w-5" />, label: 'Collections' },
    { key: '/tools', icon: <Wrench className="h-5 w-5" />, label: 'Tools' },
    { key: '/role', icon: <UserCircle className="h-5 w-5" />, label: 'Role' },
    { key: '/settings', icon: <Settings className="h-5 w-5" />, label: 'Settings' },
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
      footer={() => null}
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
