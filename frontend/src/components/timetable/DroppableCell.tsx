import React from 'react';
import { useDroppable } from '@dnd-kit/core';

interface DroppableCellProps {
  id: string;
  children: React.ReactNode;
  className?: string; // 新增
  style?: React.CSSProperties; // 新增
  data?: Record<string, unknown>;
}

const DroppableCell: React.FC<DroppableCellProps> = ({ id, children, className, style, data }) => {
  const {
    setNodeRef,
  } = useDroppable({
    id,
    data,
  });

  return (
    <div
      ref={setNodeRef}
      className={className}
      style={style}
    >
      {children}
    </div>
  );
};

export default DroppableCell;
