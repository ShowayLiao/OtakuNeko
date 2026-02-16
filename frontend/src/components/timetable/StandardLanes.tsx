import React from 'react';
import { LucideIcon } from 'lucide-react';
import DraggableItemWrapper from './DraggableItemWrapper';
import DroppableCell from './DroppableCell';
import MediaCard from '@/components/collection/MediaCard';
import { SpotlightCard } from '@lobehub/ui/awesome';
import { ScheduleItem } from '@/app/Timetable/page';

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
}

const StandardLanes: React.FC<StandardLanesProps> = ({
  standardLanes,
  scheduleItems,
  isDarkMode,
  overSlotId,
  activeDragItem,
  currentDay
}) => {
  // 根据分类和星期几获取项目
  const getItemsByCategoryAndDay = (category: string, day: number): ScheduleItem[] => {
    return scheduleItems.filter(item => item.category === category && item.day === day);
  };

  // Today高亮颜色常量
  const TODAY_HIGHLIGHT_CLASS = "bg-green-50/50 dark:bg-green-900/10";

  return (
    <div className="w-full">
      {standardLanes.map((swimlane: Swimlane, index: number) => (
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
              const items = getItemsByCategoryAndDay(swimlane.id, day);
              const isToday = day === currentDay;
              
              return (
                <DroppableCell key={day} id={`lane-${swimlane.id}-${day}`} className="h-full">
                  <div 
                    className={`p-3 ${isToday ? 'bg-blue-50/30' : ''} h-full relative`}
                    style={{ minHeight: items.length > 1 ? '80px' : '40px' }}
                  >
                    <div className="space-y-2">
                      {items.map((item) => (
                        <DraggableItemWrapper key={item.id} id={item.id}>
                          <div style={{ height: '40px', minHeight: 0 }}>
                            <SpotlightCard
                              items={[item]}
                              gap={0}
                              maxItemWidth="100%"
                              borderRadius={8}
                              columns={1}
                              style={{ height: '100%', minHeight: 0 }}
                              renderItem={(item) => (
                                <div style={{ height: '100%' }}>
                                  <MediaCard
                                    data={item}
                                    variant="timeline"
                                    currentHeight={40}
                                  />
                                </div>
                              )}
                            />
                          </div>
                        </DraggableItemWrapper>
                      ))}
                    </div>
                    
                    {/* 磁吸虚影 (Placeholder) */}
                    {overSlotId === `lane-${swimlane.id}-${day}` && activeDragItem && (
                      <div className="absolute inset-0 flex items-center justify-center opacity-30 z-10">
                        <SpotlightCard
                          items={[activeDragItem]}
                          gap={0}
                          maxItemWidth="100%"
                          borderRadius={8}
                          columns={1}
                          style={{ height: '40px', minHeight: 0, width: '100%' }}
                          renderItem={(data) => (
                            <div style={{ height: '100%' }}>
                              <MediaCard
                                data={data}
                                variant="timeline"
                                currentHeight={40}
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
          </div>
        </div>
      ))}
    </div>
  );
};

export default StandardLanes;