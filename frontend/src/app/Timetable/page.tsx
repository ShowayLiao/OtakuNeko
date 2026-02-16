'use client';

import React, { useState } from 'react';
import { DndContext, PointerSensor, useSensor, useSensors, DragOverlay } from '@dnd-kit/core';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { Utensils, Archive, BookOpen, Sparkles, Calendar } from 'lucide-react';
import { LucideIcon } from 'lucide-react';
import TimetableHeader from '@/components/header/TimetableHeader';
import TimelineBoard from '@/components/timetable/TimelineBoard';
import StandardLanes from '@/components/timetable/StandardLanes';
import MediaCard from '@/components/collection/MediaCard';
import { SpotlightCard } from '@lobehub/ui/awesome';

// 定义ScheduleItem类型
export interface ScheduleItem {
  id: string;
  title: string;
  category: 'Meal' | 'Backlog' | 'Reading' | 'New';
  day: number; // 0-6, 0=周日, 1=周一, 2=周二, 3=周三, 4=周四, 5=周五, 6=周六
  time?: string; // 可选，时间
  description?: string; // 可选，描述
}

// Mock数据
const mockScheduleItems: ScheduleItem[] = [
  // Meal - 周一/周三/周五 -> "齐木楠雄的灾难"
  { id: '1', title: '齐木楠雄的灾难', category: 'Meal', day: 1, description: '下饭番' },
  { id: '2', title: '齐木楠雄的灾难', category: 'Meal', day: 3, description: '下饭番' },
  { id: '3', title: '齐木楠雄的灾难', category: 'Meal', day: 5, description: '下饭番' },
  
  // Backlog - 周六/周日 -> "CLANNAD"
  { id: '4', title: 'CLANNAD', category: 'Backlog', day: 6, description: '补旧番' },
  { id: '5', title: 'CLANNAD', category: 'Backlog', day: 0, description: '补旧番' },
  
  // Reading - 每天 -> "迷宫饭 (漫画)"
  { id: '6', title: '迷宫饭 (漫画)', category: 'Reading', day: 0, description: '漫画' },
  { id: '7', title: '迷宫饭 (漫画)', category: 'Reading', day: 1, description: '漫画' },
  { id: '8', title: '迷宫饭 (漫画)', category: 'Reading', day: 2, description: '漫画' },
  { id: '9', title: '迷宫饭 (漫画)', category: 'Reading', day: 3, description: '漫画' },
  { id: '10', title: '迷宫饭 (漫画)', category: 'Reading', day: 4, description: '漫画' },
  { id: '11', title: '迷宫饭 (漫画)', category: 'Reading', day: 5, description: '漫画' },
  { id: '12', title: '迷宫饭 (漫画)', category: 'Reading', day: 6, description: '漫画' },
  
  // New (Schedule)
  { id: '13', title: '蔚蓝之海', category: 'New', day: 0, time: '20:00', description: '当季新番' },
  { id: '14', title: 'Gnosia', category: 'New', day: 0, time: '21:30', description: '当季新番' },
  { id: '15', title: '我推的孩子', category: 'New', day: 0, time: '22:00', description: '当季新番' },
];

// 获取当前星期几 (0-6, 0=周日, 1=周一, ..., 6=周六)
const getCurrentDay = (): number => {
  return new Date().getDay();
};

// 星期标题
const WEEK_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Today高亮颜色常量
const TODAY_HIGHLIGHT_CLASS = "bg-green-50/50 dark:bg-green-900/10";

// 泳道配置
const SWIMLANES = [
  {
    id: 'Meal',
    title: '饭点动画',
    icon: Utensils,
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-50/50 dark:bg-orange-900/20',
    borderColor: 'border-orange-200/50 dark:border-orange-800/50'
  },
  {
    id: 'Backlog',
    title: '长草动画',
    icon: Archive,
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50/50 dark:bg-blue-900/20',
    borderColor: 'border-blue-200/50 dark:border-blue-800/50'
  },
  {
    id: 'Reading',
    title: '闲暇阅读',
    icon: BookOpen,
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50/50 dark:bg-emerald-900/20',
    borderColor: 'border-emerald-200/50 dark:border-emerald-800/50'
  },
  {
    id: 'New',
    title: '新番时间',
    icon: Sparkles,
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-50/50 dark:bg-purple-900/20',
    borderColor: 'border-purple-200/50 dark:border-purple-800/50'
  },
];

// 泳道类型定义
interface Swimlane {
  id: string;
  title: string;
  icon: LucideIcon;
  color: string;
  bgColor: string;
  borderColor: string;
}

// 当前星期几高亮指示器组件
const CurrentDayIndicator: React.FC<{ day: number }> = ({ day }) => {
  const currentDay = getCurrentDay();
  const isToday = day === currentDay;
  const { isDarkMode } = useAppTheme();
  
  return (
    <div className="text-center py-3">
      <div className={`text-xs font-medium uppercase tracking-wider ${isToday ? (isDarkMode ? 'text-white' : 'text-gray-800') : (isDarkMode ? 'text-gray-400' : 'text-gray-400')}`}>
        {WEEK_DAYS[day]}
      </div>
      {isToday && (
        <div className={`mt-1 inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium ${isDarkMode ? 'bg-gray-700 text-white' : 'bg-gray-200 text-gray-800'}`}>
          Today
        </div>
      )}
    </div>
  );
};

// 主页面组件
export default function WeeklyBoardPage() {
  const { isDarkMode } = useAppTheme();
  const currentDay = getCurrentDay();
  const [scheduleItems, setScheduleItems] = useState<ScheduleItem[]>(mockScheduleItems);
  const [activeDragItem, setActiveDragItem] = useState<ScheduleItem | null>(null);
  const [overSlotId, setOverSlotId] = useState<string | null>(null);
  const [isLanesCollapsed, setIsLanesCollapsed] = useState(false);
  
  // 配置传感器
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 }
    })
  );
  
  // 根据分类和星期几获取项目
  const getItemsByCategoryAndDay = (category: string, day: number): ScheduleItem[] => {
    return scheduleItems.filter(item => item.category === category && item.day === day);
  };
  
  // 前三个分类 (Meal, Backlog, Reading)
  const standardLanes = SWIMLANES.filter(swimlane => swimlane.id !== 'New');
  
  // 新番时间分类
  const timelineLane = SWIMLANES.find(swimlane => swimlane.id === 'New');
  
  // 拖拽开始处理器
  const handleDragStart = (event: any) => {
    const { active } = event;
    const draggedItem = scheduleItems.find(item => item.id === active.id);
    setActiveDragItem(draggedItem || null);
    setOverSlotId(null);
  };
  
  // 拖拽过程处理器
  const handleDragOver = (event: any) => {
    const { over } = event;
    if (over) {
      setOverSlotId(over.id);
    } else {
      setOverSlotId(null);
    }
  };
  
  // 拖拽结束处理器
  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    
    if (!over) {
      setOverSlotId(null);
      return;
    }
    
    const activeId = active.id;
    const overId = over.id;
    
    // 查找被拖拽的项目
    const draggedItem = scheduleItems.find(item => item.id === activeId);
    if (!draggedItem) {
      setOverSlotId(null);
      return;
    }
    
    // 深拷贝项目，避免直接修改状态
    const updatedItems = [...scheduleItems];
    const itemIndex = updatedItems.findIndex(item => item.id === activeId);
    
    if (overId.startsWith('lane-')) {
      // 拖拽到标准泳道
      const parts = overId.replace('lane-', '').split('-');
      const category = parts[0];
      const day = parts.length > 1 ? parseInt(parts[1], 10) : draggedItem.day;
      
      // 更新项目
      updatedItems[itemIndex] = {
        ...draggedItem,
        category,
        day,
        time: undefined // 清空时间属性
      };
    } else if (overId.includes('-')) {
      // 拖拽到时间轴坐标 (格式: day-slotIndex)
      const [dayStr, slotIndexStr] = overId.split('-');
      const day = parseInt(dayStr, 10);
      const slotIndex = parseInt(slotIndexStr, 10);
      
      // 计算时间 (从 0 开始的 slotIndex 转换为时间)
      const hours = Math.floor(slotIndex / 3) + 18;
      const minutes = (slotIndex % 3) * 20;
      const time = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
      
      // 更新项目
      updatedItems[itemIndex] = {
        ...draggedItem,
        category: 'New',
        day,
        time
      };
    }
    
    setScheduleItems(updatedItems);
    setActiveDragItem(null);
    setOverSlotId(null);
  };
  
  return (
    <DndContext 
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className={`h-full flex flex-col overflow-hidden ${isDarkMode ? 'dark:bg-[#18181B]' : 'bg-[#FBFBFD]'}`}>
        {/* 顶部 Header 区域 - 固定不滚动 */}
        <div className="flex-none z-10">
          <TimetableHeader />
        </div>

        {/* --- FIXED AREA --- */}
        <div className={`flex-none ${isDarkMode ? 'bg-gray-900' : 'bg-white'} z-20 shadow-sm`}>
          {/* 1. Global Week Header (Mon-Sun) */}
          <div className={`flex w-full border-b ${isDarkMode ? 'border-gray-800 bg-gray-800' : 'border-gray-100 bg-white'}`}>
            {/* 左侧空白占位符 */}
            <div className="w-20"></div>
            {/* 右侧星期表头 */}
            <div className="flex-1 grid grid-cols-7">
              {WEEK_DAYS.map((day, index) => {
                const isToday = index === currentDay;
                return (
                  <div 
                    key={index} 
                    className={`text-center py-3 ${isToday ? 'bg-blue-50/30' : ''}`}
                  >
                    <div className={`text-xs font-semibold uppercase tracking-widest ${isDarkMode ? 'text-gray-400' : 'text-gray-400'}`}>
                      {day}
                    </div>
                    {isToday && (
                      <div className="mt-1 flex justify-center">
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          
          {/* 2. Standard Lanes (Meal, Backlog, Reading) - Static content */}
          {!isLanesCollapsed && (
            <StandardLanes 
              standardLanes={standardLanes}
              scheduleItems={scheduleItems}
              isDarkMode={isDarkMode}
              overSlotId={overSlotId}
              activeDragItem={activeDragItem}
              currentDay={currentDay}
            />
          )}

          {/* 3. Timeline Subheader (New!) - Moved OUT of scroll area */}
          {timelineLane && (
            <div className="flex items-center h-14 px-4">
              {/* 左侧空白占位符 */}
              <div className="w-20 flex items-center justify-center">
                <button 
                  onClick={() => setIsLanesCollapsed(!isLanesCollapsed)}
                  className={`p-1 rounded-full ${isDarkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-200'} transition-colors`}
                  aria-label={isLanesCollapsed ? '展开泳道' : '折叠泳道'}
                >
                  <svg 
                    xmlns="http://www.w3.org/2000/svg" 
                    className={`h-4 w-4 ${isDarkMode ? 'text-gray-300' : 'text-gray-600'} transform transition-transform`} 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                    style={{ transform: isLanesCollapsed ? 'rotate(0deg)' : 'rotate(180deg)' }}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </div>
              {/* 中间标题 - 胶囊样式 */}
              <div className="flex-1 flex items-center justify-center">
                <div className={`inline-flex items-center px-6 py-2 rounded-full backdrop-blur-md shadow-sm ${isDarkMode ? 'bg-gray-800/70' : 'bg-white/70'}`}>
                  <timelineLane.icon className={`${timelineLane.color} h-4 w-4 mr-2`} />
                  <span className="text-sm font-medium">新番妙妙屋</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* --- SCROLLABLE AREA (Replaced with TimelineBoard component) --- */}
        <TimelineBoard 
          scheduleItems={scheduleItems} 
          isDarkMode={isDarkMode} 
          overSlotId={overSlotId || undefined}
          activeDragItem={activeDragItem || undefined}
        />
      </div>
      
      {/* 全局悬浮残影 */}
      <DragOverlay>
        {activeDragItem && (
          <div style={{ width: '120px', zIndex: 9999 }} className="shadow-2xl opacity-90">
            <MediaCard variant="timeline" data={activeDragItem} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
