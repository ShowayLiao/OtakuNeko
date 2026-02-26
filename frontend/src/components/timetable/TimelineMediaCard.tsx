import React from 'react';
import { Tag, ActionIcon, Tooltip } from '@lobehub/ui';
import { X, Tv, Film, Book, Clock } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';


//TODO: 将这里的日程按照schedule类型重置 

// 样式配置表 (Light/Dark 分离，物理隔离)
const CATEGORY_STYLES: Record<string, { light: string; dark: string }> = {
  Meal: {
    light: 'bg-orange-50/90 border-orange-200 text-orange-900',
    dark:  'bg-orange-500/10 border-orange-400/20 shadow-[0_0_15px_-3px_rgba(249,115,22,0.15)]'
  },
  Backlog: {
    light: 'bg-blue-50/90 border-blue-200 text-blue-900',
    dark:  'bg-blue-500/10 border-blue-400/20 shadow-[0_0_15px_-3px_rgba(59,130,246,0.15)]'
  },
  Reading: {
    light: 'bg-emerald-50/90 border-emerald-200 text-emerald-900',
    dark:  'bg-emerald-500/10 border-emerald-400/20 shadow-[0_0_15px_-3px_rgba(16,185,129,0.15)]'
  },
  New: {
    light: 'bg-purple-50/90 border-purple-200 text-purple-900',
    dark:  'bg-purple-500/10 border-purple-400/20 shadow-[0_0_15px_-3px_rgba(168,85,247,0.15)]'
  },
  default: {
    light: 'bg-white/90 border-gray-200 text-gray-900',
    dark:  'bg-white/5 border-white/10'
  }
};

interface TimelineMediaCardProps {
  data: any;
  category?: string;
  currentHeight?: number;
  onOpenDetail?: (data: any) => void;
  onDelete?: (data: any) => void;
  noBorder?: boolean;
  transparent?: boolean;
  width?: number;
  isPanel?: boolean;
}

export const TimelineMediaCard = ({ data, category, currentHeight, onOpenDetail, onDelete, noBorder, transparent, width, isPanel }: TimelineMediaCardProps) => {
  const { isDarkMode } = useAppTheme();
  const cardRef = React.useRef<HTMLDivElement>(null);
  const [cardWidth, setCardWidth] = React.useState<number | null>(null);
  
  // --- 数据清洗 (逻辑封装在内部) ---
  const subject = data.subject || data;
  const title = subject?.name_cn || subject?.name || data.title;
  const rawCover = subject?.images?.large || data.cover;
  // 遇到豆瓣图片，使用本地代理接口
  const cover = rawCover?.includes('doubanio.com')
    ? `/api/proxy-image?url=${encodeURIComponent(rawCover)}`
    : rawCover;
  const score = subject?.rating?.score || data.score;
  const eps = subject?.eps || 'N/A';
  const tags = (subject?.tags || []).slice(0, 3).map((t: any) => t.name);
  
  // 计算分类样式
  const categoryKey = category || data.category || 'default';
  const styleConfig = CATEGORY_STYLES[categoryKey] || CATEGORY_STYLES.default;
  // 根据模式选择对应的样式字符串
  const activeStyle = isDarkMode ? styleConfig.dark : styleConfig.light;
  // 组合最终类名
  const themeClass = `
    ${transparent ? 'bg-transparent' : activeStyle}
    backdrop-blur-md
    ${noBorder || transparent ? 'border-none' : 'border'}
    ${transparent ? 'shadow-none' : 'shadow-sm hover:shadow-md'}
    rounded-xl
    overflow-hidden
    transition-all duration-200
  `;

  // 尺寸控制逻辑
  const sizeConfig = {
    width: '100%',
    showTags: false,
    titleLines: 1,
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(data);
  };
  
  // 宽度检测逻辑
  React.useEffect(() => {
    const updateCardWidth = () => {
      if (cardRef.current) {
        setCardWidth(cardRef.current.offsetWidth);
      }
    };
    
    // 初始更新
    updateCardWidth();
    
    // 监听窗口大小变化
    window.addEventListener('resize', updateCardWidth);
    
    // 添加 ResizeObserver 监听卡片宽度变化
    let resizeObserver: ResizeObserver | null = null;
    if (cardRef.current && typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(updateCardWidth);
      resizeObserver.observe(cardRef.current);
    }
    
    // 清理函数
    return () => {
      window.removeEventListener('resize', updateCardWidth);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, []);
  
  // ==========================================
  // 1. 响应式特征计算 (Feature Flags)
  // ==========================================
  // 优先使用传入的 width，然后使用测量的宽度，最后使用默认值
  const w = width || cardWidth || 200; // 默认宽
  const h = currentHeight || 60; // 默认高

  // 尺寸边界判定
  const isUltraCompactWidth = w <= 50;    // 极限窄：窄到连 48px 的封面都放不下
  const isCompactWidth = w <= 140;        // 偏窄：1/2 或 1/3 网格宽度
  const isVeryCompactWidth = w <= 80;     // 非常窄：1/3 或 1/4 宽度
  const isCompactHeight = h < 50;         // 偏矮：无法容纳大封面
  const isTinyHeight = h < 40;            // 极限矮：需要缩小图标

  // 核心策略修正：只要高度充足，且宽度能塞下封面，一律使用长方形大图！不被 isCompactWidth 干扰。
  // 1/4 尺寸在高度充足时也使用长方形大图，只要宽度大于 40px
  const useRectCover = !isCompactHeight && w > 40;

  // 标题显示策略：
  // 1. 如果使用了大封面，但宽度不足 90px（比如 1/4 宽），文字会被挤没，此时纯享大图（隐藏标题）
  // 2. 如果没用大封面，宽度不足 70px 时不显示标题（1/3 或 1/4 宽度），宽度大于 70px 时显示并截断标题（1/2 宽度）
  const showTitle = useRectCover ? w > 90 : w > 70;
  
  // 副标题（集数）策略：空间真正充裕时才显示
  const showSubtitle = useRectCover && !isCompactWidth;

  // 动态尺寸计算
  const iconSize = isTinyHeight ? 12 : 16;
  const coverClass = useRectCover
    ? "h-full aspect-[3/4] rounded-sm shadow-sm" // 空间大：3:4 封面，高度撑满，宽度按比例自动计算
    : `rounded-full ${isTinyHeight ? 'w-6 h-6' : 'w-8 h-8'}`; // 空间小：圆形头像

  // 选择类别图标占位
  const getCategoryIcon = () => {
    const category = data.category || 'New';
    switch (category) {
      case 'Meal': return <Tv size={iconSize} />;
      case 'Backlog': return <Film size={iconSize} />;
      case 'Reading': return <Book size={iconSize} />;
      default: return <Clock size={iconSize} />;
    }
  };

  const time = data.watch_time ?? data.start_time;
  const tooltipContent = `${title}${time ? ` - ${time}` : ''}`;

  // ==========================================
  // 2. 统一的 DOM 渲染结构
  // ==========================================
  const renderContent = () => {
    // 核心判断：如果是在 DraggablePanel 中渲染，使用宽宽度模式；否则使用窄宽度模式
    const isNarrowMode = !isPanel;

    // --- 模式 B：竖排文字模式 (在非 DraggablePanel 中渲染) ---
    if (isNarrowMode) {
      return (
        <div className="relative w-full h-full overflow-hidden group/spine">
          {/* A. 封面作为全量背景，撑满不留白 */}
          {cover ? (
            <img
              src={cover}
              alt={title}
              referrerPolicy="no-referrer"
              className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover/spine:scale-110"
            />
          ) : (
            <div className={`absolute inset-0 flex items-center justify-center ${isDarkMode ? 'bg-gray-800' : 'bg-gray-200'}`}>
              {getCategoryIcon()}
            </div>
          )}

          {/* B. 压黑背景遮罩，确保无论什么封面，白色文字都能看清 */}
          <div className="absolute inset-0 bg-black/40 group-hover/spine:bg-black/50 transition-colors" />

          {/* C. 居中的横排文字，根据高度自动调整行数 */}
          <div className="absolute inset-0 flex flex-col items-center justify-center px-1 py-0.5 pointer-events-none">
            {/* 根据高度决定文字行数 */}
            {h > 70 ? (
              // 高度足够，显示三行文字
              <span
                className="text-white text-[10px] md:text-xs font-bold leading-tight tracking-widest opacity-95 overflow-hidden text-center line-clamp-3"
                style={{
                  textShadow: '0 1px 3px rgba(0,0,0,0.8)', // 强阴影增加可读性
                  maxWidth: '90%', // 防止文字过长溢出格子
                }}
              >
                {title}
              </span>
            ) : h > 50 ? (
              // 高度适中，显示两行文字
              <span
                className="text-white text-[10px] md:text-xs font-bold leading-tight tracking-widest opacity-95 overflow-hidden text-center line-clamp-2"
                style={{
                  textShadow: '0 1px 3px rgba(0,0,0,0.8)', // 强阴影增加可读性
                  maxWidth: '90%', // 防止文字过长溢出格子
                }}
              >
                {title}
              </span>
            ) : (
              // 高度不足，显示单行文字
              <span
                className="text-white text-[10px] md:text-xs font-bold leading-none tracking-widest opacity-95 overflow-hidden truncate text-center"
                style={{
                  textShadow: '0 1px 3px rgba(0,0,0,0.8)', // 强阴影增加可读性
                  maxWidth: '90%', // 防止文字过长溢出格子
                }}
              >
                {title}
              </span>
            )}
          </div>

          {/* D. 悬浮删除按钮 (位于右侧居中) */}
          {onDelete && (
            <div className="absolute right-0 top-1/2 transform -translate-y-1/2 p-0.5 opacity-0 group-hover/spine:opacity-100 transition-opacity z-10">
              <ActionIcon
                icon={X}
                size="small"
                onClick={handleDelete}
                className="bg-black/60 text-white w-4 h-4 min-w-[16px]"
                style={{ border: 'none', color: 'white' }}
              />
            </div>
          )}
        </div>
      );
    }

    // --- 模式 A：横向图文模式 (在 DraggablePanel 中渲染) ---
    return (
      <div className="flex flex-row items-center h-full w-full overflow-hidden">
        {/* 封面：固定为 3:4 比例，靠左显示 */}
        <div className="h-full aspect-[3/4] flex-shrink-0 relative">
          {cover ? (
            <img
              src={cover}
              alt={title}
              referrerPolicy="no-referrer"
              className="w-full h-full object-cover"
            />
          ) : (
            <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}>
              {getCategoryIcon()}
            </div>
          )}
        </div>

        {/* 文字区域：横向正常显示，内部自动截断 */}
        <div className="flex flex-col flex-1 min-w-0 justify-center px-2 py-1">
          <h3 className={`font-medium text-xs truncate ${isDarkMode ? 'text-gray-200' : 'text-gray-900'}`} title={title}>
            {title}
          </h3>
          {h > 40 && (
             <span className="text-[10px] opacity-60 truncate mt-0.5">
               {time || (eps !== 'N/A' ? `${eps}集` : '')}
             </span>
          )}
        </div>
      </div>
    );
  };
  
  return (
    <Tooltip title={tooltipContent}>
      <div 
        ref={cardRef}
        className={`group flex flex-row overflow-hidden cursor-pointer
                    transition-all duration-300 group-hover:shadow-md z-10 rounded-lg
                    ${themeClass}`}
        style={{ width: sizeConfig.width, height: currentHeight }}
        onClick={() => onOpenDetail?.(data)}
      >
        {renderContent()}
      </div>
    </Tooltip>
  );
};

export default TimelineMediaCard;