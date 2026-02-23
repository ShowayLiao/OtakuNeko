import React, { useMemo } from 'react';
import { LucideIcon } from 'lucide-react';
import DraggableItemWrapper from './DraggableItemWrapper';
import DroppableCell from './DroppableCell';
import TimelineMediaCard from './TimelineMediaCard';
import ResizableCardWrapper from './ResizableCardWrapper';
import { SpotlightCard } from '@lobehub/ui/awesome';
import { BangumiItem as ScheduleItem, WatchType } from '@/services/bangumiService';

// 卡片内容高度 (不含 gap)
// 如果 MediaCard 是 variant="timeline"，通常比较矮
const CARD_HEIGHT = 48;

// 计算卡片跨列时的实际间距
// 列容器使用 p-3（12px padding），网格没有明确指定 gap
// 跨列时需要跨越：列1右padding(12) + 网格gap(0) + 列2左padding(12) = 24px
const VISUAL_GAP = 24;

interface Swimlane {
  id: string;
  title: string;
  icon: LucideIcon;
  color: string;
  bgColor: string;
}

interface StandardLanesProps {
  standardLanes: Swimlane[];
  scheduleItems: ScheduleItem[];
  isDarkMode: boolean;
  overSlotId: string | null;
  activeDragItem: ScheduleItem | null;
  currentDay: number;
  onResize?: (id: string, newDay: number, newSpan: number) => void;
  onDelete?: (id: string) => void;
}

const StandardLanes: React.FC<StandardLanesProps> = ({
  standardLanes,
  scheduleItems,
  isDarkMode,
  overSlotId,
  activeDragItem,
  currentDay,
  onResize,
  onDelete
}) => {
  // 布局计算函数
  const calculateLaneLayout = (laneItems: ScheduleItem[]) => {
    // 1. 初始化 7 天的网格，每一天是一个数组 (rows)
    // grid[dayIndex][rowIndex] = Item | 'ghost' | null
    const grid: (ScheduleItem | { type: 'ghost'; item: ScheduleItem } | null)[][] = Array(7).fill(null).map(() => []);
    
    // 2. 预先排序：按开始时间(day) -> 持续时间(duration desc) -> ID
    // 这样长条卡片会优先占据稳定位置
    const sortedItems = [...laneItems].sort((a, b) => {
      const dayA = a.watch_day ?? a.day_of_week;
      const dayB = b.watch_day ?? b.day_of_week;
      if (dayA !== dayB) return dayA - dayB;
      const durationA = a.duration ?? 1;
      const durationB = b.duration ?? 1;
      if (durationA !== durationB) return durationB - durationA; // 长的优先
      return a.id.localeCompare(b.id);
    });

    // 3. 贪心算法填坑 (Tetris)
    sortedItems.forEach(item => {
      // 使用 watch_day 代替 day_of_week
      const startDay = item.watch_day ?? item.day_of_week;
      const duration = item.duration ?? 1;
      const endDay = Math.min(startDay + duration, 7); // 防止溢出

      // 寻找一个在 [startDay, endDay) 区间内都为空闲的 rowIndex
      let rowIndex = 0;
      while (true) {
        let isRowAvailable = true;
        for (let d = startDay; d < endDay; d++) {
          if (grid[d][rowIndex] !== undefined) { // 该位置已被占用
            isRowAvailable = false;
            break;
          }
        }
        
        if (isRowAvailable) break; // 找到了！
        rowIndex++; // 这一行不行，试下一行
      }

      // 填入网格
      for (let d = startDay; d < endDay; d++) {
        // 如果这一天目前的行数还不够，先补齐 undefined/null
        while (grid[d].length < rowIndex) {
          grid[d].push(null);
        }
        // 标记位置
        // 如果是第一天，放入实体 Item；否则放入 'ghost' 标记
        grid[d][rowIndex] = (d === startDay) ? item : { type: 'ghost', item };
      }
    });

    return grid;
  };

  // Today高亮颜色常量
  const TODAY_HIGHLIGHT_CLASS = "bg-green-50/50 dark:bg-green-900/10";

  // 缓存按分类分组的项目
  const itemsByCategory = useMemo(() => {
    const map = new Map<string, ScheduleItem[]>();
    standardLanes.forEach(lane => {
      // 根据 watch_type 决定分类，而不是使用原始的 category 字段
      let filterFunction: (item: ScheduleItem) => boolean;
      switch (lane.id) {
        case 'Meal':
          filterFunction = (item: ScheduleItem) => item.watch_type === WatchType.MEAL;
          break;
        case 'Backlog':
          filterFunction = (item: ScheduleItem) => item.watch_type === WatchType.LONG_GRASS;
          break;
        case 'Reading':
          filterFunction = (item: ScheduleItem) => item.watch_type === WatchType.LEISURE;
          break;
        default:
          filterFunction = (item: ScheduleItem) => item.watch_type === WatchType.NEW;
      }
      map.set(lane.id, scheduleItems.filter(filterFunction));
    });
    return map;
  }, [scheduleItems, standardLanes]);

  // 缓存布局计算结果
  const laneLayouts = useMemo(() => {
    const map = new Map<string, (ScheduleItem | { type: 'ghost'; item: ScheduleItem } | null)[][]>();
    standardLanes.forEach(lane => {
      const items = itemsByCategory.get(lane.id) || [];
      map.set(lane.id, calculateLaneLayout(items));
    });
    return map;
  }, [itemsByCategory, standardLanes]);

  return (
    <div className="w-full">
      {standardLanes.map((swimlane: Swimlane, index: number) => {
        // 获取缓存的布局
        const laneGrid = laneLayouts.get(swimlane.id) || Array(7).fill(null).map(() => []);
        
        return (
          <div key={swimlane.id} className={`flex w-full ${index > 0 ? (isDarkMode ? 'border-t border-gray-600' : 'border-t border-gray-200') : ''}`}>
            {/* 左侧标签 */}
            <div className={`w-20 flex-none relative flex items-center justify-center ${isDarkMode ? 'bg-gray-900' : 'bg-white'}`}>
              <div className={`absolute left-0 top-0 bottom-0 w-1 ${swimlane.color.replace('text-', 'bg-')}`}></div>
              <div className="flex flex-col items-center p-2">
                <swimlane.icon className={`${swimlane.color} h-5 w-5 mb-1`} />
                <span className={`text-xs font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  {swimlane.title}
                </span>
              </div>
            </div>
            {/* 右侧7列 */}
            <div className="flex-1 grid grid-cols-7">
              {[0, 1, 2, 3, 4, 5, 6].map((day) => {
                const isToday = day === currentDay;
                // 获取当天的列数据
                const columnData = laneGrid[day] || [];

                return (
                  <DroppableCell key={day} id={`lane-${swimlane.id}-${day}`} className="h-full">
                    <div 
                      className={`p-3 ${isToday ? 'bg-blue-50/30' : ''} h-full relative`}
                      style={{ minHeight: `${columnData.length * CARD_HEIGHT}px`, overflow: 'visible' }}
                      data-column
                    >
                      <div className="flex flex-col gap-3 h-full min-h-[60px]">
                        {columnData.map((slot, rowIndex) => {
                          // --- 情况 A: 空位 (Spacer) ---
                          // 必须渲染一个透明块来占位，防止下面的卡片上浮
                          if (slot === null || slot === undefined) {
                            return (
                              <div 
                                key={`spacer-${rowIndex}`} 
                                className="w-full shrink-0"
                                style={{ height: `${CARD_HEIGHT}px` }}
                              />
                            );
                          }

                          // --- 情况 B: 幽灵卡片 (Ghost) ---
                          if (typeof slot === 'object' && 'type' in slot && slot.type === 'ghost') {
                            return (
                              <div 
                                key={`ghost-${slot.item.id}-${day}`} 
                                className="invisible pointer-events-none w-full shrink-0"
                                style={{ height: `${CARD_HEIGHT}px` }}
                              >
                                {/* 渲染一个不可见的 Card 撑开真实高度 */}
                                <div style={{ height: `${CARD_HEIGHT}px`, minHeight: 0 }}>
                                  <SpotlightCard
                                    items={[slot.item]}
                                    gap={0}
                                    maxItemWidth="100%"
                                    borderRadius={8}
                                    columns={1}
                                    style={{ height: '100%', minHeight: 0 }}
                                    renderItem={(item) => (
                                      <div style={{ height: '100%' }}>
                                        <TimelineMediaCard
                                          data={item}
                                          currentHeight={CARD_HEIGHT}
                                          onDelete={(data) => onDelete?.(data.id)}
                                        />
                                      </div>
                                    )}
                                  />
                                </div>
                              </div>
                            );
                          }

                          // --- 情况 C: 实体卡片 (Real Item) ---
                          const realItem = 'type' in slot ? slot.item : slot;
                          return (
                            <div 
                              key={realItem.id}
                              className="relative w-full shrink-0"
                              style={{ height: `${CARD_HEIGHT}px` }}
                            >
                              <DraggableItemWrapper id={realItem.id}>
                                <ResizableCardWrapper
                                  id={realItem.id}
                                  day={day}
                                  duration={realItem.duration ?? 1}
                                  gap={VISUAL_GAP}
                                  onResize={onResize}
                                >
                                  <div style={{ height: `${CARD_HEIGHT}px`, minHeight: 0 }}>
                                    <SpotlightCard
                                      items={[realItem]}
                                      gap={0}
                                      maxItemWidth="100%"
                                      borderRadius={8}
                                      columns={1}
                                      style={{ height: '100%', minHeight: 0 }}
                                      renderItem={(item) => (
                                        <div style={{ height: '100%' }}>
                                          <TimelineMediaCard
                                          data={item}
                                          currentHeight={CARD_HEIGHT}
                                          onDelete={(data) => onDelete?.(data.id)}
                                        />
                                        </div>
                                      )}
                                    />
                                  </div>
                                </ResizableCardWrapper>
                              </DraggableItemWrapper>
                            </div>
                          );
                        })}

                        {/* [修复] 将虚影移到这里 (flex-col 内部)，作为列表的最后一项 */}
                        {overSlotId === `lane-${swimlane.id}-${day}` && activeDragItem && (
                          <div 
                            className="w-full opacity-30 z-10 shrink-0" // 修改样式：移除 absolute/center，添加 shrink-0
                            style={{ height: `${CARD_HEIGHT}px` }} // 确保高度一致
                          >
                            <SpotlightCard
                              items={[activeDragItem]}
                              gap={0}
                              maxItemWidth="100%"
                              borderRadius={8}
                              columns={1}
                              style={{ height: '100%', minHeight: 0, width: '100%' }}
                              renderItem={(data) => (
                                <div style={{ height: '100%' }}>
                                  <TimelineMediaCard
                                  data={data}
                                  currentHeight={CARD_HEIGHT}
                                  onDelete={(data) => onDelete?.(data.id)}
                                />
                                </div>
                              )}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  </DroppableCell>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default StandardLanes;