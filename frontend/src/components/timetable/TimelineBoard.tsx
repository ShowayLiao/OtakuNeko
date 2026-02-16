import React, { useState, useRef, useEffect } from 'react';
import MediaCard from '@/components/collection/MediaCard';
import DraggableItemWrapper from './DraggableItemWrapper';
import DroppableCell from './DroppableCell';
import { SpotlightCard } from '@lobehub/ui/awesome';

// 定义 ScheduleItem 类型
export interface ScheduleItem {
  id: string;
  title: string;
  category: 'Meal' | 'Backlog' | 'Reading' | 'New';
  day: number; // 0-6, 0=周日, 1=周一, 2=周二, 3=周三, 4=周四, 5=周五, 6=周六
  time?: string; // 可选，时间
  description?: string; // 可选，描述
}

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

// 获取当前星期几 (0-6, 0=周日, 1=周一, ..., 6=周六)
const getCurrentDay = (): number => {
  return new Date().getDay();
};

interface TimelineBoardProps {
  scheduleItems: ScheduleItem[];
  isDarkMode: boolean;
  overSlotId?: string;
  activeDragItem?: any;
}

const TimelineBoard: React.FC<TimelineBoardProps> = ({ scheduleItems, isDarkMode, overSlotId, activeDragItem }) => {
  const [slotHeight, setSlotHeight] = useState(DEFAULT_SLOT_HEIGHT);
  const timelineContainerRef = useRef<HTMLDivElement>(null);
  const currentDay = getCurrentDay();
  
  // 根据分类和星期几获取项目
  const getItemsByCategoryAndDay = (category: string, day: number): ScheduleItem[] => {
    return scheduleItems.filter(item => item.category === category && item.day === day);
  };
  
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
            {Array.from({ length: END_HOUR - START_HOUR + 1 }).map((_, index) => {
              const hour = START_HOUR + index;
              const topPosition = index * (slotHeight * SLOTS_PER_HOUR); // 每小时高度
              
              return (
                <div 
                  key={hour} 
                  className="absolute left-0 right-0 flex items-center justify-center px-2"
                  style={{ 
                    top: `${topPosition}px`,
                    transform: index === 0 ? 'translateY(0)' : (hour === END_HOUR ? 'translateY(-100%)' : 'translateY(-50%)'),
                    alignItems: index === 0 ? 'flex-start' : (hour === END_HOUR ? 'flex-end' : 'center')
                  }}
                >
                  <span className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                    {hour.toString().padStart(2, '0')}:00
                  </span>
                </div>
              );
            })}
          </div>
          
          {/* Right: Grid Cards (grid-rows-24) */}
          <div className="flex-1">
            {/* 卡片 Grid */}
            <div className="grid grid-cols-7 min-h-full">
              {[0, 1, 2, 3, 4, 5, 6].map((day) => {
                const items = getItemsByCategoryAndDay('New', day);
                const isToday = day === currentDay;
                
                // 按startSlot分组items，处理并排显示
                const groupedItems = items.reduce((groups: Record<number, ScheduleItem[]>, item) => {
                  if (!item.time) return groups;
                  const startSlot = getStartSlot(item.time);
                  if (!groups[startSlot]) {
                    groups[startSlot] = [];
                  }
                  groups[startSlot].push(item);
                  return groups;
                }, {});
                
                return (
                  <div 
                  key={day} 
                  className={`relative ${isToday ? 'bg-blue-50/30' : ''} p-3`}
                  style={{ 
                    minHeight: `${TOTAL_SLOTS * slotHeight}px`,
                    zIndex: 0
                  }}
                >
                    {/* 生成所有时间槽的DroppableCell */}
                    {Array.from({ length: TOTAL_SLOTS }).map((_, slotIndex) => {
                      const slotId = `${day}-${slotIndex}`; // 直接使用 slotIndex 作为 ID 部分
                      const startSlot = slotIndex + 1; // 时间槽从1开始
                      
                      // 检查当前时间槽是否有番剧
                      const hasItems = Object.entries(groupedItems).some(([strSlot, items]) => {
                        return parseInt(strSlot, 10) === startSlot;
                      });
                      
                      // 计算精确坐标
                      const topPosition = slotIndex * slotHeight;

                      return (
                        <DroppableCell 
                          key={slotId} 
                          id={slotId}
                          // 强制绝对定位，钉死在格子里
                          style={{
                            position: 'absolute',
                            top: `${topPosition}px`,
                            height: `${slotHeight}px`,
                            left: 0,
                            right: 0,
                            zIndex: 1 // 确保可放置区域在最上层
                          }}
                        >
                          <div 
                            className="h-full w-full p-[1px] relative"
                            style={{ boxSizing: 'border-box' }}
                          >
                            {/* 渲染番剧卡片 */}
                            {hasItems && Object.entries(groupedItems).map(([strSlot, items]) => {
                              const slot = parseInt(strSlot, 10);
                              if (slot !== startSlot) return null;
                               
                              // 如果有多个item在同一个slot，使用flex布局并排显示
                              if (items.length > 1) {
                                return (
                                  <div key={slot} className="h-full flex gap-1">
                                    {items.map((item) => (
                                      <div key={item.id} className="flex-1 h-full">
                                        <DraggableItemWrapper id={item.id}>
                                          <div style={{ height: '100%', width: '100%', minHeight: 0 }}>
                                            <SpotlightCard
                                              items={[item]}
                                              gap={0}
                                              maxItemWidth="100%"
                                              borderRadius={8}
                                              columns={1}
                                              style={{ height: '100%', minHeight: 0 }}
                                              renderItem={(data) => (
                                                <div style={{ height: '100%', overflow: 'hidden' }}>
                                                  <MediaCard
                                                    data={data}
                                                    variant="timeline"
                                                    currentHeight={slotHeight}
                                                  />
                                                </div>
                                              )}
                                            />
                                          </div>
                                        </DraggableItemWrapper>
                                      </div>
                                    ))}
                                  </div>
                                );
                              }
                               
                              // 单个item的情况
                              return items.map((item) => {
                                if (!item.time) return null;
                                 
                                return (
                                  <DraggableItemWrapper key={item.id} id={item.id}>
                                    <div style={{ height: '100%', width: '100%', minHeight: 0 }}>
                                      <SpotlightCard
                                        items={[item]}
                                        gap={0}
                                        maxItemWidth="100%"
                                        borderRadius={8}
                                        columns={1}
                                        style={{ height: '100%', minHeight: 0 }}
                                        renderItem={(data) => (
                                          <div style={{ height: '100%', overflow: 'hidden' }}>
                                            <MediaCard
                                              data={data}
                                              variant="timeline"
                                              currentHeight={slotHeight}
                                            />
                                          </div>
                                        )}
                                      />
                                    </div>
                                  </DraggableItemWrapper>
                                );
                              });
                            })}  
                            
                            {/* 磁吸虚影 (Placeholder) */}
                            {overSlotId === slotId && activeDragItem && (
                              <div className="absolute inset-0 flex items-center justify-center opacity-30 z-10">
                                <SpotlightCard
                                  items={[activeDragItem]}
                                  gap={0}
                                  maxItemWidth="100%"
                                  borderRadius={8}
                                  columns={1}
                                  style={{ height: '100%', width: '100%', minHeight: 0 }}
                                  renderItem={(data) => (
                                    <div style={{ height: '100%', overflow: 'hidden' }}>
                                      <MediaCard
                                        data={data}
                                        variant="timeline"
                                        currentHeight={slotHeight}
                                      />
                                    </div>
                                  )}
                                />
                              </div>
                            )}
                          </div>
                        </DroppableCell>
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