"use client";
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import { MessageSquare, Grid, CalendarDays, UserCircle, Settings } from 'lucide-react';
import { ActionIcon, Flexbox, SideNav } from '@lobehub/ui';
import { theme } from 'antd';
import { ThemeSwitcher } from '@/features/Theme/ThemeSwitcher';
import { ThemeModeSwitcher } from '@/features/Theme/ThemeModeSwitcher';

export const DesktopSidebar = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { token } = theme.useToken();
  const [activeKey, setActiveKey] = useState<string>(pathname || '');

  const handleSelect = (key: string) => {
    setActiveKey(key);
    router.push(key);
  };

  return (
    <SideNav
      style={{
        background: token.colorBgContainer,
        borderRight: `1px solid ${token.colorBorder}`,
        height: '100vh'
      }}
      topActions={
        <>
          <ActionIcon
            active={activeKey === '/'}
            color={activeKey === '/' ? token.colorPrimary : undefined}
            icon={MessageSquare }
            onClick={() => handleSelect('/')}
            size="large"
          />
          <ActionIcon
            active={activeKey === '/collections'}
            color={activeKey === '/collections' ? token.colorPrimary : undefined}
            icon={Grid}
            onClick={() => handleSelect('/collections')}
            size="large"
          />
          <ActionIcon
            active={activeKey === '/Timetable'}
            color={activeKey === '/Timetable' ? token.colorPrimary : undefined}
            icon={CalendarDays}
            onClick={() => handleSelect('/Timetable')}
            size="large"
          />
          <ActionIcon
            active={activeKey === '/Personal'}
            color={activeKey === '/Personal' ? token.colorPrimary : undefined}
            icon={UserCircle}
            onClick={() => handleSelect('/Personal')}
            size="large"
          />
        </>
      }
      bottomActions={
        <Flexbox
          direction="vertical"
          gap={8}
          style={{ padding: '8px 0' }}
        >
          <ThemeSwitcher />
          <ThemeModeSwitcher />
          <ActionIcon
            active={activeKey === '/settings'}
            color={activeKey === '/settings' ? token.colorPrimary : undefined}
            icon={Settings}
            onClick={() => handleSelect('/settings')}
            size="large"
          />
        </Flexbox>
      }
    />
  );
};
