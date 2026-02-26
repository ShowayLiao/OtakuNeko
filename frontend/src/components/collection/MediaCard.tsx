import { Tag, ActionIcon, Tooltip } from '@lobehub/ui';
import { Rss, Plus, Tv, Clock, Film, Book, X } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';
import BilibiliIcon from './BilibiliIcon';

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

interface MediaCardProps {
  data: any;
  category?: string; // 新增：用于决定配色
  variant?: 'compact' | 'standard' | 'large' | 'timeline'; // 定义多种尺寸
  onOpenDetail?: (data: any) => void;
  onRSS?: (data: any) => void;
  onDelete?: (data: any) => void;
  currentHeight?: number; // 传入当前容器高度
}

export const MediaCard = ({ data, category, variant = 'standard', onOpenDetail, onRSS, onDelete, currentHeight }: MediaCardProps) => {
  const { isDarkMode } = useAppTheme();
  
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
  const tags = (subject?.tags || []).slice(0, variant === 'compact' ? 1 : 3).map((t: any) => t.name);
  
  // 计算分类样式
  const categoryKey = category || data.category || 'default';
  const styleConfig = CATEGORY_STYLES[categoryKey] || CATEGORY_STYLES.default;
  // 根据模式选择对应的样式字符串
  const activeStyle = isDarkMode ? styleConfig.dark : styleConfig.light;
  // 组合最终类名
  const themeClass = `
    ${activeStyle}
    backdrop-blur-md
    border
    shadow-sm hover:shadow-md
    rounded-xl
    overflow-hidden
    transition-all duration-200
  `;

  // 尺寸控制逻辑
  const sizeConfig = {
    compact: { width: '100%', showTags: false, titleLines: 1 },
    standard: { width: '100%', showTags: true, titleLines: 2 },
    large: { width: '100%', showTags: true, titleLines: 2 },
    timeline: { width: '100%', showTags: false, titleLines: 1 },
  };

  const handleSearch = (e: React.MouseEvent) => {
    e.stopPropagation();
    const searchKeyword = title || subject?.name;
    if (searchKeyword) {
      window.open(`https://search.bilibili.com/all?keyword=${encodeURIComponent(searchKeyword)}`, '_blank');
    }
  };

  const handleRSS = (e: React.MouseEvent) => {
    e.stopPropagation();
    onRSS?.(data);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(data);
  };

  if (variant === 'timeline') {
    // 确定当前高度模式
    const getHeightMode = () => {
      if (!currentHeight) return 'medium'; // 默认中等高度
      if (currentHeight < 40) return 'small';
      if (currentHeight < 50) return 'medium';
      return 'large';
    };
    
    const heightMode = getHeightMode();
    
    // 选择图标
    const getCategoryIcon = () => {
      const category = data.category || 'New';
      switch (category) {
        case 'Meal': return <Tv size={heightMode === 'small' ? 12 : 16} />;
        case 'Backlog': return <Film size={heightMode === 'small' ? 12 : 16} />;
        case 'Reading': return <Book size={heightMode === 'small' ? 12 : 16} />;
        default: return <Clock size={heightMode === 'small' ? 12 : 16} />;
      }
    };
    
    // 准备 Tooltip 内容
    const tooltipContent = `${title}${data.time ? ` - ${data.time}` : ''}`;
    
    // 渲染不同高度模式的内容
    const renderContent = () => {
      switch (heightMode) {
        case 'small':
          return (
            <div className="flex items-center justify-between gap-2 h-full pl-2">
              <div className="flex items-center gap-2">
                <div className={`flex-shrink-0 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                  {getCategoryIcon()}
                </div>
                <span className={`text-xs ${isDarkMode ? 'text-gray-200' : 'text-gray-900'} truncate`}>
                  {title || '无标题'}
                </span>
              </div>
              {onDelete && (
                <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <ActionIcon
                    icon={X}
                    title="删除"
                    size="small"
                    onClick={handleDelete}
                    variant="borderless"
                    style={{ 
                      color: isDarkMode ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)',
                      backgroundColor: 'transparent',
                      border: 'none'
                    }}
                  />
                </div>
              )}
            </div>
          );
          
        case 'medium':
          return (
            <div className="flex items-center justify-between gap-2 h-full pl-1">
              <div className="flex items-center gap-2">
                <div className={`w-8 h-8 flex-shrink-0 relative overflow-hidden rounded-full ${isDarkMode ? 'bg-gray-700' : 'bg-gray-100'}`}>
                  {cover ? (
                    <img 
                      src={cover} 
                      alt={title} 
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      {getCategoryIcon()}
                    </div>
                  )}
                </div>
                <span className={`text-sm ${isDarkMode ? 'text-gray-200' : 'text-gray-900'} truncate`}>
                  {title || '无标题'}
                </span>
              </div>
              {onDelete && (
                <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <ActionIcon
                    icon={X}
                    title="删除"
                    size="small"
                    onClick={handleDelete}
                    variant="borderless"
                    style={{ 
                      color: isDarkMode ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)',
                      backgroundColor: 'transparent',
                      border: 'none'
                    }}
                  />
                </div>
              )}
            </div>
          );
          
        case 'large':
          return (
            <div className="flex flex-row items-center h-full overflow-hidden">
              {/* 左侧封面 - 3:4 比例 */}
              <div className={`w-12 aspect-[3/4] flex-none relative overflow-hidden ${isDarkMode ? 'bg-gray-700' : 'bg-gray-100'}`}>
                {cover ? (
                  <img 
                    src={cover} 
                    alt={title} 
                    referrerPolicy="no-referrer"
                    className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
                  />
                ) : (
                  <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                    {getCategoryIcon()}
                  </div>
                )}
              </div>

              {/* 右侧内容 */}
              <div className={`p-2 flex flex-col flex-1 gap-1 overflow-hidden`}>
                <h3 className={`font-medium text-sm ${isDarkMode ? 'text-gray-200' : 'text-gray-900'} line-clamp-2 leading-tight`} title={title}>
                  {title || '无标题'}
                </h3>
                <span className={`text-xs ${isDarkMode ? 'text-gray-400' : 'text-gray-500'} truncate`}>
                  {data.time || eps !== 'N/A' ? `${eps}集` : ''}
                </span>
              </div>
              
              {/* 删除按钮 */}
              {onDelete && (
                <div className="p-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <ActionIcon
                    icon={X}
                    title="删除"
                    size="small"
                    onClick={handleDelete}
                    variant="borderless"
                    style={{ 
                      color: isDarkMode ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)',
                      backgroundColor: 'transparent',
                      border: 'none'
                    }}
                  />
                </div>
              )}
            </div>
          );
          
        default:
          return (
            <div className="flex items-center justify-between gap-2 h-full pl-2">
              <div className="flex items-center gap-2">
                <div className={`w-8 h-8 flex-shrink-0 relative overflow-hidden rounded-full ${isDarkMode ? 'bg-gray-700' : 'bg-gray-100'}`}>
                  {cover ? (
                    <img 
                      src={cover} 
                      alt={title} 
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      {getCategoryIcon()}
                    </div>
                  )}
                </div>
                <span className={`text-sm ${isDarkMode ? 'text-gray-200' : 'text-gray-900'} truncate`}>
                  {title || '无标题'}
                </span>
              </div>
              {onDelete && (
                <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <ActionIcon
                    icon={X}
                    title="删除"
                    size="small"
                    onClick={handleDelete}
                    variant="borderless"
                    style={{ 
                      color: isDarkMode ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)',
                      backgroundColor: 'transparent',
                      border: 'none'
                    }}
                  />
                </div>
              )}
            </div>
          );
      }
    };
    
    return (
      <Tooltip title={tooltipContent}>
        <div 
          className={`group flex flex-row h-full overflow-hidden cursor-pointer
                    transition-all duration-300 group-hover:shadow-md z-10 rounded-lg
                    ${themeClass}`}
          style={{ width: sizeConfig[variant].width }}
          onClick={() => onOpenDetail?.(data)}
        >
          {renderContent()}
        </div>
      </Tooltip>
    );
  }

  // Default layout for other variants
  return (
    <div 
      className={`group flex flex-col h-full overflow-hidden cursor-pointer
                    transition-all duration-200 hover:shadow-md
                    ${themeClass}`}
      style={{ width: sizeConfig[variant].width }}
      onClick={() => onOpenDetail?.(data)}
    >
      {/* 封面区域 */}
      <div className="aspect-[2/3] w-full relative overflow-hidden">
        {cover ? (
          <img 
            src={cover} 
            alt={title} 
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>No Image</div>
        )}
        
        {/* 评分角标 */}
        {score && (
          <div className="absolute top-2 left-2 bg-black/60 backdrop-blur-md text-white text-xs font-bold px-1.5 py-0.5 rounded flex items-center gap-1 shadow-sm z-20">
            <span className="text-yellow-400">★</span>{score}
          </div>
        )}

        {/* 侧边工具栏 (在 compact 模式下可以隐藏或缩小) */}
        <div className={`absolute top-0 right-0 bottom-0 z-10 w-11
                        flex flex-col items-center justify-center gap-3 py-3
                        ${isDarkMode ? 'bg-gray-900/70 backdrop-blur-sm border-l border-white/10' : 'bg-white/60 backdrop-blur-sm border-l border-black/10'}
                        transform-gpu will-change-transform transform translate-x-full group-hover:translate-x-0 
                        transition-transform duration-300 cubic-bezier(0.2, 0, 0, 1)`}>

          {/* B站搜索 */}
          <ActionIcon
            icon={BilibiliIcon}
            title="B站搜索"
            glass
            size={variant === 'compact' ? 'small' : 'middle'}
            onClick={handleSearch}
            variant="outlined"
            style={{ color: isDarkMode ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)' }}
          />

          {/* 订阅 RSS */}
          <ActionIcon
            icon={Rss}
            title="RSS 订阅"
            glass
            size={variant === 'compact' ? 'small' : 'middle'}
            onClick={handleRSS}
            variant="outlined"
            style={{ color: isDarkMode ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)' }}
          />

          {/* 更多/详情 (底部) */}
          <div className="mt-auto">
            <ActionIcon
              icon={Plus} // 或者 Info 图标
              title="查看详情"
              glass
              size="small"
              variant="outlined"
              style={{ color: isDarkMode ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)' }}
              // 这里不需要 onClick，因为点击空白处本身就会触发卡片的 onOpenDetail
            />
          </div>

        </div>
      </div>

      {/* 信息区域：务必移除所有 bg-color */}
      <div className="p-3 flex flex-col flex-1 gap-1 relative z-20 min-w-0">
        {/* 标题：强制设定 Light/Dark 颜色 */}
        <h3 className={`font-bold text-sm leading-tight truncate line-clamp-2 ${isDarkMode ? 'text-gray-200' : 'text-gray-900'}`} title={title}>
          {title || '无标题'}
        </h3>
        
        {/* 辅助信息：稍微淡一点 */}
        <div className="flex items-center justify-between gap-2 mt-auto">
          {sizeConfig[variant].showTags && (
            <div className="flex flex-wrap gap-1">
              {tags.map((tag: string, index: number) => (
                <Tag key={index} size="small" style={{ opacity: 0.8, fontSize: '10px', height: '20px', backgroundColor: isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)' }}>
                  {tag}
                </Tag>
              ))}
            </div>
          )}
          <span className={`text-xs font-mono whitespace-nowrap ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
            {eps !== 'N/A' ? `${eps}集` : ''}
          </span>
        </div>
      </div>
    </div>
  );
};

export default MediaCard;