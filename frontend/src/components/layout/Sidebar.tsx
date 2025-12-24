"use client";

import { MessageSquare, Grid, Wrench, UserCircle, Settings } from 'lucide-react';

interface SidebarProps {
  className?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({ className = '' }) => {
  return (
    <aside className={`w-64 h-screen bg-white border-r border-gray-100 flex flex-col ${className}`}>
      {/* Logo区域 */}
      <div className="p-6 border-b border-gray-100">
        <h1 className="text-xl font-bold text-gray-900">OtakuNeko</h1>
      </div>
      
      {/* 导航菜单 */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {[
            { icon: <MessageSquare className="h-5 w-5" />, label: 'Chat', active: true, href: '/' },
            { icon: <Grid className="h-5 w-5" />, label: 'Collections', active: false, href: '/collections' },
            { icon: <Wrench className="h-5 w-5" />, label: 'Tools', active: false, href: '/tools' },
            { icon: <UserCircle className="h-5 w-5" />, label: 'Role', active: false, href: '#' },
            { icon: <Settings className="h-5 w-5" />, label: 'Settings', active: false, href: '/settings' },
          ].map((item, index) => (
            <li key={index}>
              <a
                href={item.href}
                className={`flex items-center gap-3 px-4 py-2 rounded-lg transition-colors ${item.active ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:bg-gray-50'}`}
              >
                {item.icon}
                <span>{item.label}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
};
