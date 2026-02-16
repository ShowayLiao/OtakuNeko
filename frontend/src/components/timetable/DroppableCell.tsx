import React from 'react';
import { useDroppable } from '@dnd-kit/core';

interface DroppableCellProps {
  id: string;
  children: React.ReactNode;
  className?: string; // 新增
  style?: React.CSSProperties; // 新增
}

const DroppableCell: React.FC<DroppableCellProps> = ({ id, children, className, style }) => {
  const {
    setNodeRef,
  } = useDroppable({
    id,
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