"use client";

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Header } from '../components/header/Header';
import { DesktopSidebar } from '@/features/Sidebar';

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
  
  // 判断是否为聊天页面，逻辑覆盖根路径和包含 /chat 的路径
  const isChatPage = pathname === '/' || pathname?.includes('/chat');

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
    /**
     * 1. 最外层容器
     * 使用 fixed 定位锁死视口，禁止 body 滚动
     */
    <div style={{ 
      position: 'fixed', 
      top: 0, 
      left: 0, 
      width: '100vw', 
      height: '100vh', 
      display: 'flex', 
      flexDirection: 'row',
      overflow: 'hidden',
      background: 'var(--color-bg-layout, #fff)', // 使用主题变量
      color: 'var(--color-text, #000)'
    }}>
      
      {/* 左侧全局导航栏 (Sidebar) */}
      <DesktopSidebar />

      <div style={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column', 
        height: '100%', 
        position: 'relative',
        minWidth: 0 // 核心：防止子元素（如长代码块）撑破 Flex 容器
      }}>
        
        {/* 全局顶栏 (Header) */}
        <Header />
        <main style={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column', 
          position: 'relative', 
          overflow: 'hidden', // 关键：屏蔽此层滚动，防止出现双滚动条
          minHeight: 0        // 核心：允许子 Flex 元素在空间不足时收缩
        }}>
          {isChatPage ? (
            /* 聊天模式：
               1. 直接渲染 children (ChatPage)
               2. 确保它继承 flex: 1 和 height: 100%
            */
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
              {children}
            </div>
          ) : (
            /* 普通页面模式：
               1. 允许在此层级进行垂直滚动
               2. 应用 maxWidth 和内边距
            */
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <div style={contentStyle} className={className}>
                {children}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default APPLayout;