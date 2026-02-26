'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { DndContext, PointerSensor, useSensor, useSensors, DragOverlay, pointerWithin } from '@dnd-kit/core';
import { useAppTheme } from '@/components/providers/LobeProvider';
import {
  ActionIcon,
  Avatar,
  Button,
  Flexbox,
  Header,
  Popover,
  PopoverGroup,
  Tag,
  toast,
} from '@lobehub/ui';
import { LobeHub } from '@lobehub/ui/brand';
import {
  ChevronDown,
  ChevronUp,
  CloudDownload,
  HardDriveDownload,
  Save,
  CalendarArrowUp,
  ListTodo,
  CalendarPlus,
  User,
  Settings,
  LogOut,
  CloudSync,
  Share,
  Utensils,
  Archive,
  BookOpen,
  Sparkles,
  Calendar,
  Trash2
} from 'lucide-react';
import { LucideIcon } from 'lucide-react';
import { getBangumiCalendar, syncBangumiCalendar, BangumiItem as ScheduleItem, WatchType } from '@/services/bangumiService';
import { ScheduleBase, deleteAllSchedules, getSchedules } from '@/services/scheduleService';
import TimetableHeader from '@/components/header/TimetableHeader';
import TimelineBoard from '@/components/timetable/TimelineBoard';
import StandardLanes from '@/components/timetable/StandardLanes';
import TimelineMediaCard from '@/components/timetable/TimelineMediaCard';
import CollectionPanel from '@/components/timetable/DraggablePanel';
import { ExportTickTickModal } from '@/components/Modal/ExportTickTickModal';
import { SpotlightCard } from '@lobehub/ui/awesome';



// 获取当前星期几 (0-6, 0=周一, 1=周二, ..., 6=周日)
const getCurrentDay = (): number => {
  const day = new Date().getDay();
  // 转换为 0=周一, 1=周二, ..., 6=周日
  return day === 0 ? 6 : day - 1;
};

// 星期标题
const WEEK_DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

// Today高亮颜色常量
const TODAY_HIGHLIGHT_CLASS = "bg-green-50/50 dark:bg-green-900/10";

// 现代化导航项组件
const NavItem = ({
  children,
  items,
  icon: Icon,
}: {
  children: string;
  icon?: React.ElementType;
  items: { icon?: React.ElementType; label: string; tag?: string; onClick?: () => void }[];
}) => (
  <Popover
    arrow={false}
    placement="bottomLeft"
    trigger="hover"
    content={
      <Flexbox gap={6} style={{ minWidth: 160, padding: '8px' }}>
        <div
          style={{
            color: 'var(--lobe-color-text-3)',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.5px',
            padding: '4px 8px',
            textTransform: 'uppercase',
          }}
        >
          {children}
        </div>
        {items.map((item) => (
          <Flexbox
            horizontal
            align="center"
            key={item.label}
            onClick={item.onClick}
            style={{
              borderRadius: 8,
              cursor: 'pointer',
              padding: '8px 12px',
              transition: 'all 0.2s',
            }}
            className="hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            {item.icon && <item.icon size={16} style={{ marginRight: 10 }} />}
            <span style={{ flex: 1, fontSize: 14 }}>{item.label}</span>
            {item.tag && (
              <Tag color={item.tag === 'New' ? 'purple' : 'blue'} style={{ marginLeft: 8 }}>
                {item.tag}
              </Tag>
            )}
          </Flexbox>
        ))}
      </Flexbox>
    }
  >
    <Button icon={Icon ? <Icon size={16} /> : undefined} style={{ gap: 6 }} type="text">
      {children}
      <ChevronDown size={14} style={{ opacity: 0.6 }} />
    </Button>
  </Popover>
);

// 泳道配置
const SWIMLANES = [
  {
    id: 'Meal',
    title: '饭点动画',
    icon: Utensils,
    color: 'text-orange-700 dark:text-orange-400',
    bgColor: 'bg-orange-50 dark:bg-orange-900/20',
    borderColor: 'border-orange-100 dark:border-orange-800/30'
  },
  {
    id: 'Backlog',
    title: '长草动画',
    icon: Archive,
    color: 'text-blue-700 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
    borderColor: 'border-blue-100 dark:border-blue-800/30'
  },
  {
    id: 'Reading',
    title: '闲暇阅读',
    icon: BookOpen,
    color: 'text-emerald-700 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-900/20',
    borderColor: 'border-emerald-100 dark:border-emerald-800/30'
  },
  {
    id: 'New',
    title: '新番时间',
    icon: Sparkles,
    color: 'text-purple-700 dark:text-purple-400',
    bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    borderColor: 'border-purple-100 dark:border-purple-800/30'
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
  const [scheduleItems, setScheduleItems] = useState<ScheduleItem[]>([]);
  const [activeDragItem, setActiveDragItem] = useState<ScheduleItem | null>(null);
  const [overSlotId, setOverSlotId] = useState<string | null>(null);
  const [isLanesCollapsed, setIsLanesCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isTickTickModalOpen, setIsTickTickModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  
  // 组件加载时自动获取日程数据
  useEffect(() => {
    const loadSchedules = async () => {
      setIsLoading(true);
      setError(null);
      try {
        // 调用 getSchedules API 获取数据
        const schedules = await getSchedules();
        // 更新 scheduleItems 状态
        setScheduleItems(schedules);
        console.log('自动加载日程数据成功，共', schedules.length, '条记录');
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : '获取日程数据失败';
        setError(errorMessage);
        console.error('自动加载日程数据失败:', errorMessage);
      } finally {
        setIsLoading(false);
      }
    };
    
    loadSchedules();
  }, []); // 空依赖数组，只在组件挂载时执行一次
  
  // 配置传感器
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 }
    })
  );
  
  // 根据分类和星期几获取项目
  const getItemsByCategoryAndDay = (category: string, day: number): ScheduleItem[] => {
    // 由于我们已经移除了 category 字段，这里需要根据 watch_type 来判断
    let watchType: WatchType | undefined;
    switch (category) {
      case 'Meal':
        watchType = WatchType.MEAL;
        break;
      case 'Backlog':
        watchType = WatchType.LONG_GRASS;
        break;
      case 'Reading':
        watchType = WatchType.LEISURE;
        break;
      case 'New':
        watchType = WatchType.NEW;
        break;
    }
    return scheduleItems.filter(item => item.watch_type === watchType && item.watch_day === day);
  };
  
  // 前三个分类 (Meal, Backlog, Reading)
  const standardLanes = SWIMLANES.filter(swimlane => swimlane.id !== 'New');
  
  // 新番时间分类
  const timelineLane = SWIMLANES.find(swimlane => swimlane.id === 'New');
  
  // 辅助方法：去除ID前缀，获取真实ID
  const getRealId = (id: string) => id.replace(/^(panel-|board-|timeline-|lane-)/, '');
  
  // 拖拽开始处理器
  const handleDragStart = (event: any) => {
    const { active } = event;
    
    // 首先尝试从active.data中获取拖动的项目（适用于从CollectionPanel拖动的情况）
    if (active.data && active.data.current) {
      setActiveDragItem(active.data.current);
    } else {
      // 然后尝试从scheduleItems中查找（适用于从已有泳道拖动的情况）
      const realId = getRealId(String(active.id));
      const draggedItem = scheduleItems.find(item => `${item.subject.source}-${item.subject.source_id}` === realId);
      setActiveDragItem(draggedItem || null);
    }
    
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
  
  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    
    if (typeof setOverSlotId === 'function') setOverSlotId(null);
    if (typeof setActiveDragItem === 'function') setActiveDragItem(null);

    if (!over) return;

    // 强制转换为字符串，防止因 Number 和 String 不一致导致匹配失败
    const activeIdWithPrefix = String(active.id);
    const realActiveId = getRealId(activeIdWithPrefix);
    const overId = String(over.id);

    // 在调用 setScheduleItems 之前，先将当前的 activeDragItem 状态提取到一个局部变量中
    const currentActiveItem = activeDragItem;

    setScheduleItems((prevItems) => {
      // 首先尝试从prevItems中找到activeItem（适用于从已有泳道拖动的情况）
      let activeItem = prevItems.find((item) => `${item.subject.source}-${item.subject.source_id}` === realActiveId);
      
      // 如果找不到，优先将外层的 currentActiveItem 赋值给 activeItem
      if (!activeItem) {
        activeItem = currentActiveItem || undefined;
      }
      
      // 如果还是找不到，尝试从active.data中获取（适用于从CollectionPanel拖动的情况）
      if (!activeItem && active.data && active.data.current) {
        activeItem = active.data.current;
      }
      
      if (!activeItem) return prevItems;

      let newDay = activeItem.watch_day ?? 0;
      let newTime = activeItem.watch_time || '';
      let newType = activeItem.watch_type || WatchType.NEW;
      let newDuration = activeItem.duration || 1;

      if (overId.startsWith('lane-')) {
        // 情况 A: 拖入标准泳道
        const parts = overId.split('-');
        if (parts.length >= 3) {
          const laneStr = parts[1].toUpperCase();
          newDay = parseInt(parts[2], 10);
          
          // 使用更宽松的匹配，防止 swimlane.id 格式不同导致匹配失败
          if (laneStr.includes('MEAL') || laneStr === '1') newType = WatchType.MEAL;
          else if (laneStr.includes('READING') || laneStr === '2' || laneStr.includes('LEISURE')) newType = WatchType.LEISURE;
          else if (laneStr.includes('BACKLOG') || laneStr === '3' || laneStr.includes('LONG')) newType = WatchType.LONG_GRASS;
          else if (laneStr.includes('NEW') || laneStr === '4') newType = WatchType.NEW;
          
          newTime = ''; // 移入泳道后，清空具体时间
          newDuration = 1; // 标准泳道中默认持续时间为1天
        }
      } else if (overId.includes('-') && !overId.startsWith('board-')) {
        // 情况 B: 拖入时间网格，排除拖到其他卡片上的情况
        const parts = overId.split('-');
        if (parts.length === 2) {
          let visualDay = parseInt(parts[0], 10);
          const slotIndex = parseInt(parts[1], 10);
          
          const START_HOUR = 18;
          const hour = START_HOUR + Math.floor(slotIndex / 3);
          const minute = (slotIndex % 3) * 20;
          
          let logicalDay = visualDay;
          
          // 🌟 核心跨天修正：如果落入的是深夜档(hour>=24)
          // 视觉上它属于 visualDay 的深夜，但在真实逻辑中，它的物理时间是下一天的凌晨。
          // 所以存储数据的 watch_day 必须是视觉天数 +1，才能被正确渲染在深夜档网格。
          if (hour >= 24) {
            logicalDay = (visualDay + 1) % 7;
          }
          
          newDay = logicalDay;
          const displayHour = hour >= 24 ? hour - 24 : hour;
          newTime = `${displayHour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
          newType = WatchType.NEW;
          newDuration = 1; // 时间网格中默认持续时间为1天
        }
      } else if (overId.startsWith('board-')) {
        // 情况 C: 拖到其他卡片上，忽略此操作
        return prevItems;
      } else {
        return prevItems;
      }

      // 检查项目是否已存在于prevItems中
      const itemExists = prevItems.some((item) => `${item.subject.source}-${item.subject.source_id}` === realActiveId);
      
      if (itemExists) {
        // 如果项目已存在，更新它
        return prevItems.map((item) =>
          `${item.subject.source}-${item.subject.source_id}` === realActiveId
            ? {
                ...item,
                watch_day: newDay,
                watch_time: newTime,
                watch_type: newType,
                duration: newDuration
              }
            : item
        );
      } else {
        // 如果项目不存在（从CollectionPanel拖动的新项），添加它
        return [
          ...prevItems,
          {
            ...activeItem,
            watch_day: newDay,
            watch_time: newTime,
            watch_type: newType,
            duration: newDuration
          }
        ];
      }
    });
  };

  // 处理卡片拉伸事件
  const handleResize = useCallback((id: string, newDay: number, newDuration: number) => {
    setScheduleItems(prev => prev.map(item => {
      if (`${item.subject.source}-${item.subject.source_id}` === id) {
        return {
          ...item,
          watch_day: newDay,
          duration: newDuration
        };
      }
      return item;
    }));
  }, []);
  
  // 处理卡片删除事件
  const handleDelete = useCallback((id: string) => {
    setScheduleItems(prev => prev.filter(item => `${item.subject.source}-${item.subject.source_id}` !== id));
  }, []);
  
  // 处理获取 Bangumi 日历数据
  const handleFetchBangumiCalendar = async () => {
    setIsLoading(true);
    setError(null);
    try {
      // 清空现有的卡片
      setScheduleItems([]);
      
      // 调用 syncBangumiCalendar 函数获取数据
      const bangumiItems = await syncBangumiCalendar();
      
      // 过滤掉 watch_time 为空的卡片
      const validItems = bangumiItems.filter(item => item.watch_time !== '未知' && item.watch_time !== null);
      
      // 确保所有项目都有正确的 watch_type 和默认 duration
      const updatedItems = validItems.map(item => {
        return {
          ...item,
          watch_type: item.watch_type || WatchType.NEW,
          duration: item.duration ?? 1
        };
      });
      
      // 更新卡片数据
      setScheduleItems(updatedItems);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取 Bangumi 日历数据失败');
    } finally {
      setIsLoading(false);
    }
  };
  
  // 同步处理函数
  const handleSyncCloud = () => {
    console.log('同步云端');
  };
  
  const handleSyncLocal = () => {
    console.log('同步本地');
  };
  
  // 导出与保存处理函数
  const handleSaveSchedule = () => {
    console.log('保存当前排期');
  };

  // 保存日程成功回调
  const handleSaveSuccess = () => {
    console.log('日程保存成功');
  };
  
  // 同步数据回调
  const handleSyncData = (data: any[]) => {
    console.log('同步数据成功，接收到的数据:', data);
    // 更新 scheduleItems 状态，渲染到页面上
    setScheduleItems(data);
  };
  
  // 搜索处理函数
  const handleSearch = (value: string) => {
    setSearchQuery(value);
  };
  
  // 清空所有卡片
  const handleClearAll = async () => {
    try {
      // 调用后端 API 删除所有排班记录
      await deleteAllSchedules();
      // 清空页面上的排班记录
      setScheduleItems([]);
      // 显示成功提示
      toast.success('所有日程已清空');
    } catch (error) {
      console.error('清空所有日程失败:', error);
      toast.error('清空所有日程失败，请重试');
    }
  };
  
  // 同步菜单
  const syncMenu = (
    <div className="flex flex-col w-36 p-1">
      <div onClick={handleSyncCloud} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md cursor-pointer text-sm transition-colors">
        <CloudDownload size={14} /> <span>同步云端</span>
      </div>
      <div onClick={handleSyncLocal} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md cursor-pointer text-sm transition-colors">
        <HardDriveDownload size={14} /> <span>同步本地</span>
      </div>
    </div>
  );
  
  return (
    <DndContext 
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      collisionDetection={pointerWithin}
    >
      <div className={`h-full flex flex-col overflow-hidden ${isDarkMode ? 'dark:bg-neutral-950' : 'bg-white'}`}>
        {/* 顶部 Header 区域 - 固定不滚动 */}
        <div className="flex-none z-10">
          <TimetableHeader 
            schedules={scheduleItems}
            onSaveSuccess={handleSaveSuccess}
            onSyncData={handleSyncData}
            onExportTickTick={() => setIsTickTickModalOpen(true)}
            onSearch={handleSearch}
          />
        </div>

        {/* 主内容区域 - 包含左侧时间轴和右侧控制面板 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧内容区域 */}
          <div className="flex-1 flex flex-col overflow-hidden">
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
                  onResize={handleResize}
                  onDelete={handleDelete}
                />
              )}

              <Header
                logo={
                  <PopoverGroup contentLayoutAnimation>
                    <Flexbox horizontal gap={4} justify="center" style={{ width: '100%' }}>
                      {/* 核心强引导操作：一键导入 */}
                      <Button
                        type="text"
                        onClick={handleFetchBangumiCalendar}
                        disabled={isLoading}
                        icon={<CalendarPlus size={16} style={{ color: '#9333ea' }} />}
                        variant="text"
                        style={{ height: '36px' }}
                      >
                        一键导入新番
                      </Button>
                      {/* 折叠/展开标准泳道 */}
                    </Flexbox>
                  </PopoverGroup>
                }
                actions={
                  <PopoverGroup contentLayoutAnimation>
                    <Flexbox horizontal gap={4} justify="center" style={{ width: '100%' }}>
                      {/* 清空所有卡片 */}
                      <ActionIcon
                        icon={<Trash2 size={16} />}
                        title="清空所有卡片"
                        onClick={handleClearAll}
                        variant="borderless"
                        size="small"
                      />
                      {/* 导出菜单 */}
                      <ActionIcon
                        icon={isLanesCollapsed ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        title={isLanesCollapsed ? "展开标准泳道" : "折叠标准泳道"}
                        onClick={() => setIsLanesCollapsed(!isLanesCollapsed)}
                        variant="borderless"
                        size="small"
                      />
                    </Flexbox>
                  </PopoverGroup>
                }
                className="h-12"
              />
            </div>

            {/* --- SCROLLABLE AREA (Replaced with TimelineBoard component) --- */}
            <TimelineBoard 
              scheduleItems={scheduleItems} 
              isDarkMode={isDarkMode} 
              currentDay={currentDay}
              overSlotId={overSlotId || undefined}
              activeDragItem={activeDragItem || undefined}
              onDelete={handleDelete}
              isLoading={isLoading}
              error={error || undefined}
            />
          </div>
          
          {/* 右侧可拖拽面板 */}
          <CollectionPanel searchQuery={searchQuery} />
        </div>
      </div>
      
      {/* 全局悬浮残影 */}
      <DragOverlay dropAnimation={null}>
        {activeDragItem && (
          <div
            style={{ width: '200px', height: '60px', zIndex: 9999 }}
            className="shadow-2xl opacity-90 rounded-lg overflow-hidden bg-white dark:bg-gray-800"
          >
            <TimelineMediaCard
              data={activeDragItem}
              currentHeight={60}
            />
          </div>
        )}
      </DragOverlay>
      
      {/* 批量导出到滴答清单 Modal */}
      <ExportTickTickModal
        open={isTickTickModalOpen}
        onCancel={() => setIsTickTickModalOpen(false)}
        items={scheduleItems}
      />
    </DndContext>
  );
}
