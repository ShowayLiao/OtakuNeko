import React, { useRef, useState, useEffect } from 'react';

interface ResizableCardWrapperProps {
  id: string;
  day: number;  // 新增：当前所在的星期索引 (0-6)
  duration: number; // 当前持续时长
  children: React.ReactNode;
  // 修改回调：同时支持修改开始时间(day)和持续时长(duration)
  onResize?: (id: string, newDay: number, newDuration: number) => void;
  columnWidth?: number;
  gap?: number;
}

const ResizableCardWrapper: React.FC<ResizableCardWrapperProps> = ({
  id,
  day,
  duration = 1,
  children,
  onResize,
  columnWidth,
  gap = 12,
}) => {
  const [isResizing, setIsResizing] = useState<null | 'left' | 'right'>(null);
  const [hoveredHandle, setHoveredHandle] = useState<null | 'left' | 'right'>(null);
  const [tempDayOffset, setTempDayOffset] = useState(0);
  const [tempDuration, setTempDuration] = useState(duration);
  const cardRef = useRef<HTMLDivElement>(null);
  const isResizingRef = useRef<null | 'left' | 'right'>(null);
  const startXRef = useRef<number>(0);
  const startDayRef = useRef<number>(day);
  const startDurationRef = useRef<number>(duration);
  const columnWidthRef = useRef<number>(columnWidth || 100);

  // 计算当前卡片宽度
  const getCurrentWidth = (currentDuration: number = duration) => {
    return currentDuration * columnWidthRef.current + (currentDuration - 1) * gap;
  };

  // 处理指针按下事件
  const handlePointerDown = (e: React.PointerEvent, handle: 'left' | 'right') => {
    e.stopPropagation();
    e.preventDefault();
    setIsResizing(handle);
    isResizingRef.current = handle;
    startXRef.current = e.clientX;
    startDayRef.current = day;
    startDurationRef.current = duration;
    setTempDayOffset(0);
    setTempDuration(duration);
    
    // 添加全局事件监听器
    document.addEventListener('pointermove', handlePointerMove);
    document.addEventListener('pointerup', handlePointerUp);
    document.addEventListener('pointercancel', handlePointerUp);
  };

  // 处理指针移动事件
  const handlePointerMove = (e: PointerEvent) => {
    if (!isResizingRef.current || !onResize) return;
    
    const deltaX = e.clientX - startXRef.current;
    const gridSize = columnWidthRef.current + gap;
    const gridDiff = Math.round(deltaX / gridSize);
    
    let newDay = startDayRef.current;
    let newDuration = startDurationRef.current;
    
    if (isResizingRef.current === 'right') {
      // 右侧手柄：只修改 duration
      newDuration = Math.max(1, startDurationRef.current + gridDiff);
    } else {
      // 左侧手柄：修改 day 和 duration
      newDay = Math.max(0, startDayRef.current + gridDiff);
      newDuration = Math.max(1, startDurationRef.current - gridDiff);
    }
    
    // 更新临时状态用于视觉反馈
    setTempDayOffset(newDay - startDayRef.current);
    setTempDuration(newDuration);
  };

  // 处理指针释放事件
  const handlePointerUp = (e: PointerEvent) => {
    if (isResizingRef.current && onResize) {
      const deltaX = e.clientX - startXRef.current;
      const gridSize = columnWidthRef.current + gap;
      const gridDiff = Math.round(deltaX / gridSize);
      
      let newDay = startDayRef.current;
      let newDuration = startDurationRef.current;
      
      if (isResizingRef.current === 'right') {
        newDuration = Math.max(1, startDurationRef.current + gridDiff);
      } else {
        newDay = Math.max(0, startDayRef.current + gridDiff);
        newDuration = Math.max(1, startDurationRef.current - gridDiff);
      }
      
      // 调用回调更新数据
      onResize(id, newDay, newDuration);
    }
    
    // 重置状态
    setIsResizing(null);
    isResizingRef.current = null;
    setTempDayOffset(0);
    setTempDuration(duration);
    
    // 移除全局事件监听器
    document.removeEventListener('pointermove', handlePointerMove);
    document.removeEventListener('pointerup', handlePointerUp);
    document.removeEventListener('pointercancel', handlePointerUp);
  };

  // 初始化列宽
  useEffect(() => {
    if (!columnWidth && cardRef.current) {
      // 尝试从父元素计算列宽
      const parent = cardRef.current.closest('[data-column]');
      if (parent) {
        columnWidthRef.current = parent.clientWidth;
      }
    }
  }, [columnWidth]);

  // 计算当前渲染使用的 duration
  const renderDuration = isResizing ? tempDuration : duration;
  // 计算当前渲染使用的偏移量
  const renderOffset = tempDayOffset * (columnWidthRef.current + gap);

  return (
    <div
      ref={cardRef}
      className="relative"
      style={{
        width: `calc(100% * ${renderDuration} + ${(renderDuration - 1) * gap}px)`,
        zIndex: 10,
        position: 'relative',
        transform: `translateX(${renderOffset}px)`,
        transition: isResizing ? 'none' : 'transform 0.2s ease',
      }}
    >
      {/* 左侧调整手柄 */}
      <div
        className="absolute left-0 top-0 bottom-0 w-4 cursor-ew-resize z-10"
        style={{
          opacity: hoveredHandle === 'left' || isResizing === 'left' ? 0.5 : 0,
          backgroundColor: 'blue',
        }}
        onPointerDown={(e) => handlePointerDown(e, 'left')}
        onPointerEnter={() => setHoveredHandle('left')}
        onPointerLeave={() => setHoveredHandle(null)}
      />
      
      {/* 卡片内容 */}
      <div className="relative">
        {children}
      </div>
      
      {/* 右侧调整手柄 */}
      <div
        className="absolute right-0 top-0 bottom-0 w-4 cursor-ew-resize z-10"
        style={{
          opacity: hoveredHandle === 'right' || isResizing === 'right' ? 0.5 : 0,
          backgroundColor: 'blue',
        }}
        onPointerDown={(e) => handlePointerDown(e, 'right')}
        onPointerEnter={() => setHoveredHandle('right')}
        onPointerLeave={() => setHoveredHandle(null)}
      />
    </div>
  );
};

export default ResizableCardWrapper;