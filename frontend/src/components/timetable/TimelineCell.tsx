import React, { useState } from 'react';
import DroppableCell from './DroppableCell';
import DraggableItemWrapper from './DraggableItemWrapper';
import TimelineMediaCard from './TimelineMediaCard';
import SubjectModal from '../Modal/SubjectModal';
import { BangumiItem as ScheduleItem } from '@/services/bangumiService';

interface TimelineCellProps {
  dayIndex: number;
  slotIndex: number;
  items: ScheduleItem[];
  isOver: boolean;
  activeDragItem?: any;
  onDelete?: (id: string) => void;
  slotHeight: number;
}

const TimelineCell: React.FC<TimelineCellProps> = ({
  dayIndex,
  slotIndex,
  items,
  isOver,
  activeDragItem,
  onDelete,
  slotHeight
}) => {
  const slotId = `${dayIndex}-${slotIndex}`;
  const topPosition = slotIndex * slotHeight;
  const [isSubjectModalOpen, setIsSubjectModalOpen] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState<any>(null);

  const handleOpenDetail = (item: any) => {
    // 确保 item 数据格式正确
    const formattedItem = {
      ...item,
      // 确保 subject 字段存在
      subject: item.subject || item,
      // 确保 collection 字段存在
      collection: item.collection || {}
    };
    setSelectedSubject(formattedItem);
    setIsSubjectModalOpen(true);
  };

  return (
    <>
      <DroppableCell
        key={slotId}
        id={slotId}
        style={{
          position: 'absolute',
          top: `${topPosition}px`,
          height: `${slotHeight}px`,
          left: 0,
          right: 0,
          zIndex: 1
        }}
      >
        <div
          className="h-full w-full p-[1px] relative overflow-hidden"
          style={{ boxSizing: 'border-box' }}
        >
          {/* 渲染番剧卡片 */}
          {items.length > 0 && (
            items.length > 1 ? (
              <div className="h-full w-full flex gap-1">
                {items.map((item) => (
                  <div key={`${item.subject.source}-${item.subject.source_id}`} className="flex-1 h-full min-w-0">
                    <DraggableItemWrapper id={`board-${item.subject.source}-${item.subject.source_id}`} data={item}>
                      <div style={{ height: '100%', width: '100%', minHeight: 0 }}>
                        <TimelineMediaCard
                          data={item}
                          currentHeight={slotHeight}
                          onDelete={(data) => onDelete?.(`${data.subject.source}-${data.subject.source_id}`)}
                          onOpenDetail={handleOpenDetail}
                          width={items.length > 1 ? undefined : undefined}
                        />
                      </div>
                    </DraggableItemWrapper>
                  </div>
                ))}
              </div>
            ) : (
              items.map((item) => (
                <DraggableItemWrapper key={`${item.subject.source}-${item.subject.source_id}`} id={`board-${item.subject.source}-${item.subject.source_id}`} data={item}>
                  <div style={{ height: '100%', width: '100%', minHeight: 0 }}>
                    <TimelineMediaCard
                      data={item}
                      currentHeight={slotHeight}
                      onDelete={(data) => onDelete?.(`${data.subject.source}-${data.subject.source_id}`)}
                      onOpenDetail={handleOpenDetail}
                    />
                  </div>
                </DraggableItemWrapper>
              ))
            )
          )}

          {/* 磁吸虚影 (Placeholder) */}
          {isOver && activeDragItem && (
            <div className="absolute inset-0 flex items-center justify-center opacity-30 z-10">
              <div style={{ height: '100%', width: '100%', minHeight: 0 }}>
                <TimelineMediaCard
                  data={activeDragItem}
                  currentHeight={slotHeight}
                  onDelete={(data) => onDelete?.(`${data.subject.source}-${data.subject.source_id}`)}
                />
              </div>
            </div>
          )}
        </div>
      </DroppableCell>

      {/* 条目详情模态框 */}
      <SubjectModal
        isOpen={isSubjectModalOpen}
        onClose={() => {
          setIsSubjectModalOpen(false);
          setSelectedSubject(null);
        }}
        initialValues={selectedSubject}
      />
    </>
  );
};

const arePropsEqual = (prevProps: TimelineCellProps, nextProps: TimelineCellProps): boolean => {
  // 比较 items 引用和内容
  const itemsAreEqual = () => {
    if (prevProps.items === nextProps.items) {
      return true;
    }
    if (prevProps.items.length !== nextProps.items.length) {
      return false;
    }
    for (let i = 0; i < prevProps.items.length; i++) {
      const prevItem = prevProps.items[i];
      const nextItem = nextProps.items[i];
      if (prevItem.subject.source !== nextItem.subject.source || prevItem.subject.source_id !== nextItem.subject.source_id) {
        return false;
      }
    }
    return true;
  };

  // 比较 slotHeight
  const slotHeightEqual = prevProps.slotHeight === nextProps.slotHeight;

  // 隔离 activeDragItem 变化
  if (!prevProps.isOver && !nextProps.isOver) {
    // 该格子之前和现在都没有被拖拽悬停，渲染结果不受 activeDragItem 影响
    return itemsAreEqual() && slotHeightEqual;
  } else {
    // 格子正在被悬停，或者 isOver 状态发生切换，需要比较更多属性
    const isOverEqual = prevProps.isOver === nextProps.isOver;
    const prevDragItemKey = prevProps.activeDragItem?.subject?.source && prevProps.activeDragItem?.subject?.source_id
      ? `${prevProps.activeDragItem.subject.source}-${prevProps.activeDragItem.subject.source_id}`
      : null;
    const nextDragItemKey = nextProps.activeDragItem?.subject?.source && nextProps.activeDragItem?.subject?.source_id
      ? `${nextProps.activeDragItem.subject.source}-${nextProps.activeDragItem.subject.source_id}`
      : null;
    const activeDragItemIdEqual = prevDragItemKey === nextDragItemKey;
    return isOverEqual && itemsAreEqual() && activeDragItemIdEqual && slotHeightEqual;
  }
};

export default React.memo(TimelineCell, arePropsEqual);