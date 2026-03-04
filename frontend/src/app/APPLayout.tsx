"use client";

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { DesktopSidebar } from '@/features/Sidebar';
import { theme } from 'antd';
import { ToastHost } from '@lobehub/ui';

export interface APPLayoutProps {
  children: ReactNode;
  className?: string;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full';
  padding?: 'none' | 'sm' | 'md' | 'lg';
}


export const APPLayout = ({
  children,
  className,
  maxWidth = 'xl',
  padding = 'md'
}: APPLayoutProps) => {
  const pathname = usePathname();

  const { token } = theme.useToken();
  
  // 判断是否为聊天页面，逻辑覆盖根路径和包含 /chat 的路径
  const isFullScreenPage = pathname === '/' || pathname?.includes('/chat') || pathname === '/collections' || pathname === '/Timetable' || pathname === '/Personal';

  // 样式映射表
  const paddingMap: Record<string, string> = {
    none: '0',
    sm: '16px',
    md: '24px',
    lg: '32px'
  };

  const maxWidthMap: Record<string, string> = {
    sm: '384px',
    md: '448px',
    lg: '512px',
    xl: '576px',
    '2xl': '672px',
    full: '100%'
  };

  // 普通页面的内联样式计算
  const contentStyle = {
    width: '100%',
    maxWidth: maxWidthMap[maxWidth] || '576px',
    padding: paddingMap[padding] || '24px',
    margin: '0 auto',
  };

  return (
    <div style={{ 
      position: 'fixed', 
      top: 0, 
      left: 0, 
      width: '100vw', 
      height: '100vh', 
      display: 'flex', 
      flexDirection: 'row',
      overflow: 'hidden',
      // 3. 核心修复：直接使用 token 中的颜色
      background: token.colorBgLayout, 
      color: token.colorTextBase
    }}>
      
      <DesktopSidebar />

      <div style={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column', 
        height: '100%', 
        position: 'relative',
        minWidth: 0 
      }}>
        
        <main style={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column', 
          position: 'relative', 
          overflow: 'hidden', 
          minHeight: 0        
        }}>
          {isFullScreenPage ? (
            // ✅ 全屏模式：无 Padding，无默认滚动，高度 100%
            // 这时候你的 CollectionPage 就必须自己写 flex flex-col 和 overflow-y-auto
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
              {children}
            </div>
          ) : (
            // ❌ 普通文档模式（设置页等）：有 Padding，Layout 负责滚动
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <div style={contentStyle} className={className}>
                {children}
              </div>
            </div>
          )}
        </main>
      </div>
      <ToastHost />
    </div>
  );
};

export default APPLayout;