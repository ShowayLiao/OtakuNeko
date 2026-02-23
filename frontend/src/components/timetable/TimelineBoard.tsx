import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import DraggableItemWrapper from './DraggableItemWrapper';
import DroppableCell from './DroppableCell';
import TimelineCell from './TimelineCell';
import { SpotlightCard } from '@lobehub/ui/awesome';
import { BangumiItem as ScheduleItem, WatchType } from '@/services/bangumiService';

// 空数组常量，用于保证没有番剧的空网格每次接收到的都是同一个数组内存引用
const EMPTY_ARRAY: ScheduleItem[] = [];

interface TimelineBoardProps {
  scheduleItems: ScheduleItem[];
  isDarkMode: boolean;
}

// 星期标题
const WEEK_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// 新番时间网格配置
const START_HOUR = 18;
const END_HOUR = 26;
const SLOTS_PER_HOUR = 3; // 20分钟/格
const TOTAL_SLOTS = (END_HOUR - START_HOUR) * SLOTS_PER_HOUR; // 24格
const DEFAULT_SLOT_HEIGHT = 40; // 默认每格高度40px
const MIN_SLOT_HEIGHT = 20; // 最小每格高度20px
const MAX_SLOT_HEIGHT = 120; // 最大每格高度120px

// Today高亮颜色常量
const TODAY_HIGHLIGHT_CLASS = "bg-green-50/50 dark:bg-green-900/10";

// 计算卡片在网格中的起始行
const getStartSlot = (time: string): number => {
  const [hourStr, minuteStr] = time.split(':');
  const hour = parseInt(hourStr, 10);
  const minute = parseInt(minuteStr, 10);
  const minutesFromStart = (hour - START_HOUR) * 60 + minute;
  return Math.round(minutesFromStart / 20) + 1; // Grid行号从1开始，使用round增加磁吸感
};

// 获取当前时间在网格中的位置比例（用于绘制当前时间红线）
const getCurrentTimePosition = (): number => {
  const now = new Date();
  const currentHour = now.getHours();
  const currentMinute = now.getMinutes();
  
  // 如果当前时间在18:00之前，返回0
  if (currentHour < START_HOUR) {
    return 0;
  }
  
  // 如果当前时间在26:00之后，返回1
  if (currentHour >= END_HOUR) {
    return 1;
  }
  
  // 计算当前时间相对于18:00的分钟数
  const minutesFromStart = (currentHour - START_HOUR) * 60 + currentMinute;
  // 计算总分钟数
  const totalMinutes = (END_HOUR - START_HOUR) * 60;
  // 返回比例
  return minutesFromStart / totalMinutes;
};

interface TimelineBoardProps {
  scheduleItems: ScheduleItem[];
  isDarkMode: boolean;
  currentDay: number;
  overSlotId?: string;
  activeDragItem?: any;
  onDelete?: (id: string) => void;
  isLoading?: boolean;
  error?: string;
}

const TimelineBoard: React.FC<TimelineBoardProps> = ({ scheduleItems, isDarkMode, currentDay, overSlotId, activeDragItem, onDelete, isLoading, error }) => {
  const [slotHeight, setSlotHeight] = useState(DEFAULT_SLOT_HEIGHT);
  const timelineContainerRef = useRef<HTMLDivElement>(null);
  

  
  // 时间槽标签生成
  const timeSlots = useMemo(() => {
    return Array.from({ length: END_HOUR - START_HOUR + 1 }).map((_, index) => {
      const hour = START_HOUR + index;
      const topPosition = index * (slotHeight * SLOTS_PER_HOUR);
      return {
        hour,
        topPosition,
        label: `${hour.toString().padStart(2, '0')}:00`
      };
    });
  }, [slotHeight]);
  
  // 数据结构优化：统一计算和分配网格索引
  const itemsBySlotMap = useMemo(() => {
    const map = new Map<string, ScheduleItem[]>();
    
    // 1. 过滤出 WatchType.NEW 类型的项目
    const newItems = scheduleItems.filter(item => item.watch_type === WatchType.NEW);
    
    // 2. 预处理阶段：标准化日期和时间，处理【0点-2点】跨天逻辑
    const normalizedItems = newItems.map(item => {
      // 确定基础日期
      let baseDay = item.watch_day ?? item.day_of_week;
      if (baseDay === undefined && item.air_weekday) {
        baseDay = (item.air_weekday - 1) % 7;
      }
      
      let timeStr = item.watch_time || item.start_time || '';
      let effectiveDay = baseDay;
      let effectiveTimeStr = timeStr;
      let originalTotalMins = 0; // 用于后续排序的绝对分钟数

      if (timeStr && effectiveDay !== undefined) {
        const [hStr, mStr] = timeStr.split(':');
        const h = parseInt(hStr, 10);
        const m = parseInt(mStr, 10);
        originalTotalMins = h * 60 + m;

        // 【规则1】处理 0点到2点：归入前一天的 24~26点
        if (h >= 0 && h < 2) {
          effectiveDay = (effectiveDay - 1 + 7) % 7; // 前一天
          effectiveTimeStr = `${h + 24}:${m.toString().padStart(2, '0')}`;
        }
      }

      return {
        item,
        effectiveDay,
        effectiveTimeStr,
        originalTotalMins,
      };
    });

    // 3. 按最终的有效日期（effectiveDay）进行分组
    const itemsByDay = new Map<number, typeof normalizedItems>();
    for (let i = 0; i < 7; i++) {
      itemsByDay.set(i, []);
    }

    normalizedItems.forEach(ni => {
      if (ni.effectiveDay !== undefined) {
        itemsByDay.get(ni.effectiveDay)?.push(ni);
      }
    });

    // 4. 核心渲染阶段：对每一天的数据进行处理
    itemsByDay.forEach((dayItems, day) => {
      const morningItems: typeof normalizedItems = [];
      const normalItems: typeof normalizedItems = [];

      // 将当天番剧分离为【2点~18点】的早间番剧和其他正常番剧
      dayItems.forEach(ni => {
        if (!ni.effectiveTimeStr) return;
        const [hStr] = ni.effectiveTimeStr.split(':');
        const h = parseInt(hStr, 10);
        
        // 筛选位于当天的 2点 到 18点之间的动画
        if (h >= 2 && h < 18) {
          morningItems.push(ni);
        } else {
          normalItems.push(ni);
        }
      });

      // 【规则2】对当天的早间番剧，按原始真实播放时间进行先后排序
      morningItems.sort((a, b) => a.originalTotalMins - b.originalTotalMins);

      // 【规则3】重写早间番剧的时间（从当天的 18:00 开始，严格间隔 20 分钟）
      morningItems.forEach((ni, index) => {
        const baseHour = 18;
        const addHour = Math.floor((index * 20) / 60);
        const minute = (index * 20) % 60;
        ni.effectiveTimeStr = `${baseHour + addHour}:${minute.toString().padStart(2, '0')}`;
      });

      // 5. 合并当天所有处理完毕的番剧，计算最终 Grid 插槽并写入 Map
      const allDayItems = [...morningItems, ...normalItems];
      allDayItems.forEach(ni => {
        if (!ni.effectiveTimeStr) return;
        
        const startSlot = getStartSlot(ni.effectiveTimeStr);
        const slotIndex = startSlot - 1; // 转换为从0开始的索引
        const key = `${day}-${slotIndex}`;
        
        if (!map.has(key)) {
          map.set(key, []);
        }
        map.get(key)?.push(ni.item);
      });
    });

    return map;
  }, [scheduleItems]);
  
  // 实现 Ctrl + 滚轮缩放功能
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -2 : 2;
        setSlotHeight(h => Math.min(Math.max(h + delta, MIN_SLOT_HEIGHT), MAX_SLOT_HEIGHT));
      }
    };

    const container = timelineContainerRef.current;
    if (container) {
      container.addEventListener('wheel', handleWheel, { passive: false });
      return () => {
        container.removeEventListener('wheel', handleWheel);
      };
    }
  }, []);
  
  return (
    <div className="flex-1 relative min-h-0" id="timeline-container" ref={timelineContainerRef} style={{ scrollbarGutter: 'stable', scrollbarWidth: 'none', overflowY: 'auto', overflowX: 'visible' }}>
      {/* Hide scrollbar for Chrome, Safari and Opera */}
      <style jsx>{`
        #timeline-container::-webkit-scrollbar {
          display: none;
        }
      `}</style>
      <div className="relative" style={{ minHeight: `${TOTAL_SLOTS * slotHeight}px`, paddingBottom: '0px', overflow: 'visible' }}>
        {/* A. Background Grid Layer (Lines & Today Highlight) */}
        <div className="absolute inset-x-0 top-0 pointer-events-none min-h-full flex z-1">
          {/* Left: Time Labels background */}
          <div className="w-20 flex-none"></div>
          {/* Right: Grid background */}
          <div className="flex-1">
            {/* Layer 1: Horizontal Grid Lines (中间层) */}
            {Array.from({ length: TOTAL_SLOTS }).map((_, index) => {
              const topPosition = index * slotHeight; // 每格高度
              
              // 判断当前格子是否为整点起始格
              const isHourStart = index % SLOTS_PER_HOUR === 0;
              
              // 只显示整点的网格线
              if (!isHourStart) return null;
              
              return (
                <div 
                  key={index} 
                  className={`absolute left-0 right-0 h-px ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}
                  style={{ top: `${topPosition}px` }}
                ></div>
              );
            })} 
            
            {/* 26:00 收尾线 */}
            <div 
              className={`absolute left-0 right-0 h-px ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}
              style={{ top: `${TOTAL_SLOTS * slotHeight}px` }}
            ></div>
          </div>
        </div>
        
        {/* B. Content Layer */}
        <div className="flex min-h-full">
          {/* Left: Time Labels */}
          <div className={`w-20 flex-none ${isDarkMode ? 'bg-gray-900' : 'bg-white'} relative z-2`}>
            {/* 生成整点时间轴刻度 - 与网格线对齐 */}
            {timeSlots.map(({ hour, topPosition, label }) => (
              <div 
                key={hour} 
                className="absolute left-0 right-0 flex items-center justify-center px-2"
                style={{ 
                  top: `${topPosition}px`,
                  transform: hour === START_HOUR ? 'translateY(0)' : (hour === END_HOUR ? 'translateY(-100%)' : 'translateY(-50%)'),
                  alignItems: hour === START_HOUR ? 'flex-start' : (hour === END_HOUR ? 'flex-end' : 'center')
                }}
              >
                <span className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                  {label}
                </span>
              </div>
            ))}
          </div>
          
          {/* Right: Grid Cards (grid-rows-24) */}
          <div className="flex-1">
            {/* 加载状态 */}
            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/30 backdrop-blur-sm z-50">
                <div className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-800' : 'bg-white'} shadow-lg`}>
                  <div className="flex items-center gap-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                    <span className={`text-sm ${isDarkMode ? 'text-gray-200' : 'text-gray-800'}`}>加载中...</span>
                  </div>
                </div>
              </div>
            )}
            
            {/* 错误状态 */}
            {error && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/30 backdrop-blur-sm z-50">
                <div className={`px-4 py-2 rounded-lg ${isDarkMode ? 'bg-gray-800' : 'bg-white'} shadow-lg`}>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm ${isDarkMode ? 'text-red-400' : 'text-red-600'}`}>{error}</span>
                  </div>
                </div>
              </div>
            )}
            
            {/* 卡片 Grid */}
            <div className="grid grid-cols-7 min-h-full">
              {[0, 1, 2, 3, 4, 5, 6].map((day) => {
                const isToday = day === currentDay;
                
                return (
                  <div 
                    key={day} 
                    className={`relative ${isToday ? 'bg-blue-50/30' : ''} p-3`}
                    style={{ 
                      minHeight: `${TOTAL_SLOTS * slotHeight}px`,
                      zIndex: 0
                    }}
                  >
                    {/* 生成所有时间槽的 TimelineCell */}
                    {Array.from({ length: TOTAL_SLOTS }).map((_, slotIndex) => {
                      const slotId = `${day}-${slotIndex}`;
                      const items = itemsBySlotMap.get(slotId) || EMPTY_ARRAY;
                      const isOver = overSlotId === slotId;
                      
                      return (
                        <TimelineCell
                          key={slotId}
                          dayIndex={day}
                          slotIndex={slotIndex}
                          items={items}
                          isOver={isOver}
                          activeDragItem={activeDragItem}
                          onDelete={onDelete}
                          slotHeight={slotHeight}
                        />
                      );
                    })}
                    
                    {/* 当前时间红线 */}
                    <div 
                      className="absolute left-0 right-0 w-full h-0.5 bg-red-500 pointer-events-none z-10"
                      style={{ 
                        top: `${getCurrentTimePosition() * 100}%` 
                      }}
                    ></div>
                  </div>
                );
              })} 
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TimelineBoard;