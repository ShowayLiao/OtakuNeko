import { Tag, ActionIcon } from '@lobehub/ui';
import { Rss, Plus } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';
import BilibiliIcon from './BilibiliIcon';

interface MediaCardProps {
  data: any;
  variant?: 'compact' | 'standard' | 'large'; // 定义多种尺寸
  onOpenDetail?: (data: any) => void;
  onRSS?: (data: any) => void;
}

export const MediaCard = ({ data, variant = 'standard', onOpenDetail, onRSS }: MediaCardProps) => {
  const { isDarkMode } = useAppTheme();
  
  // --- 数据清洗 (逻辑封装在内部) ---
  const subject = data.subject || data;
  const title = subject?.name_cn || subject?.name || data.title;
  const cover = subject?.images?.large || data.cover;
  const score = subject?.rating?.score || data.score;
  const eps = subject?.eps || 'N/A';
  const tags = (subject?.tags || []).slice(0, variant === 'compact' ? 1 : 3).map((t: any) => t.name);

  // 尺寸控制逻辑
  const sizeConfig = {
    compact: { width: '100%', showTags: false, titleLines: 1 },
    standard: { width: '100%', showTags: true, titleLines: 2 },
    large: { width: '100%', showTags: true, titleLines: 2 },
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

  return (
    <div 
      className={`group flex flex-col h-full overflow-hidden cursor-pointer ${isDarkMode ? 'dark:bg-slate-800' : 'bg-white'}`}
      style={{ width: sizeConfig[variant].width }}
      onClick={() => onOpenDetail?.(data)}
    >
      {/* 封面区域 */}
      <div className={`aspect-[2/3] w-full relative overflow-hidden ${isDarkMode ? 'dark:bg-slate-900' : 'bg-slate-100'}`}>
        {cover ? (
          <img 
            src={cover} 
            alt={title} 
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'text-slate-600' : 'text-slate-300'}`}>No Image</div>
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
                        ${isDarkMode ? 'bg-slate-900/70 backdrop-blur-sm border-l border-white/10' : 'bg-white/60 backdrop-blur-sm border-l border-black/10'}
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

      {/* 信息区域 */}
      <div className={`p-3 flex flex-col flex-1 gap-2 relative ${isDarkMode ? 'bg-slate-800' : 'bg-white'} z-20`}>
        <h3 className={`font-medium text-sm ${isDarkMode ? 'text-slate-100' : 'text-slate-900'} line-clamp-${sizeConfig[variant].titleLines} leading-tight`} title={title}>
          {title || '无标题'}
        </h3>
        <div className="mt-auto flex items-center justify-between gap-2">
          {sizeConfig[variant].showTags && (
            <div className="flex flex-wrap gap-1">
              {tags.map((tag: string, index: number) => (
                <Tag key={index} size="small" style={{ opacity: 0.8, fontSize: '10px', height: '20px' }}>
                  {tag}
                </Tag>
              ))}
            </div>
          )}
          <span className={`text-xs ${isDarkMode ? 'text-slate-400' : 'text-slate-400'} font-mono whitespace-nowrap`}>
            {eps !== 'N/A' ? `${eps}集` : ''}
          </span>
        </div>
      </div>
    </div>
  );
};

export default MediaCard;