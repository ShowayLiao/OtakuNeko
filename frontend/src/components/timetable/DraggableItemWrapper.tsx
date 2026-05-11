import React from 'react';
import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { BangumiItem } from '@/services/bangumiService';

interface DraggableItemWrapperProps {
  id: string;
  children: React.ReactNode;
  data?: BangumiItem;
}

const DraggableItemWrapperInner: React.FC<DraggableItemWrapperProps> = ({ id, children, data }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    isDragging,
  } = useDraggable({
    id,
    data,
  });

  const style = {
    opacity: isDragging ? 0.3 : 1, // 拖动时原件变淡
    touchAction: 'none' as const,
    width: '100%',
    height: '100%',
    minWidth: 0,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
    >
      {children}
    </div>
  );
};

const arePropsEqual = (prev: DraggableItemWrapperProps, next: DraggableItemWrapperProps) => {
  if (prev.id !== next.id) return false;
  const prevData = prev.data;
  const nextData = next.data;
  if (!prevData && !nextData) return true;
  if (!prevData || !nextData) return false;
  return prevData.subject?.source === nextData.subject?.source
      && prevData.subject?.source_id === nextData.subject?.source_id;
};

const DraggableItemWrapper = React.memo(DraggableItemWrapperInner, arePropsEqual);
export default DraggableItemWrapper;