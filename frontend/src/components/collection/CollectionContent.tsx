import { Empty, Tag ,ActionIcon} from '@lobehub/ui';
import { SpotlightCard } from '@lobehub/ui/awesome';
import { Search, Rss, Plus, Calendar, MonitorPlay } from 'lucide-react'; // 引入图标
import { useAppTheme } from '@/components/providers/LobeProvider';
import { useState } from 'react';
import SmartSubscriptionModal from '@/components/Modal/SmartSubscriptionModal';

const BilibiliIcon = (props: any) => {
  // 从 props 中分离出 style 和其他属性，以免冲突
  const { style, ...rest } = props;

  return (
    <svg
      viewBox="0 0 1024 1024"
      version="1.1"
      xmlns="http://www.w3.org/2000/svg"
      // 默认给一个宽高，防止父级没传大小时完全消失
      width="1em"
      height="1em"
      // 关键修复 1：强制使用填充色，并去除描边
      fill="currentColor"
      stroke="none"
      // 关键修复 2：透传所有 props (className, onClick 等)
      {...rest}
      // 关键修复 3：合并样式，确保 fill 生效
      style={{ 
        ...style, 
        fill: 'currentColor', 
        stroke: 'none' 
      }}
    >
      <path d="M306.005333 117.632L444.330667 256h135.296l138.368-138.325333a42.666667 42.666667 0 0 1 60.373333 60.373333L700.330667 256H789.333333A149.333333 149.333333 0 0 1 938.666667 405.333333v341.333334a149.333333 149.333333 0 0 1-149.333334 149.333333h-554.666666A149.333333 149.333333 0 0 1 85.333333 746.666667v-341.333334A149.333333 149.333333 0 0 1 234.666667 256h88.96L245.632 177.962667a42.666667 42.666667 0 0 1 60.373333-60.373334zM789.333333 341.333333h-554.666666a64 64 0 0 0-63.701334 57.856L170.666667 405.333333v341.333334a64 64 0 0 0 57.856 63.701333L234.666667 810.666667h554.666666a64 64 0 0 0 63.701334-57.856L853.333333 746.666667v-341.333334A64 64 0 0 0 789.333333 341.333333zM341.333333 469.333333a42.666667 42.666667 0 0 1 42.666667 42.666667v85.333333a42.666667 42.666667 0 0 1-85.333333 0v-85.333333a42.666667 42.666667 0 0 1 42.666666-42.666667z m341.333334 0a42.666667 42.666667 0 0 1 42.666666 42.666667v85.333333a42.666667 42.666667 0 0 1-85.333333 0v-85.333333a42.666667 42.666667 0 0 1 42.666667-42.666667z" />
    </svg>
  );
};



interface CollectionContentProps {
  items: any[];
  onOpenDetail?: (item: any) => void; // 假设你有个点击打开详情的回调
}

export default function CollectionContent({ items = [], onOpenDetail }: CollectionContentProps) {
  const { isDarkMode } = useAppTheme();
  const [isSubscriptionModalOpen, setIsSubscriptionModalOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<any>(null);
  
  if (!items || items.length === 0) {
    return <Empty description="暂无内容" image="simple" />;
  }

  return (
    <div className="p-4">
      <SpotlightCard
        items={items}
        gap={20}
        maxItemWidth={180}
        borderRadius={12}
        columns={5}
        
        renderItem={(item) => {
          // --- 1. 数据清洗 ---
          const isSubject = !!item.subject;
          const subject = isSubject ? item.subject : item; // 兼容逻辑
          
          const title = subject?.name_cn || subject?.name || item.title;
          const cover = subject?.images?.large || item.cover;
          const score = subject?.rating?.score || item.rating?.score || item.score;
          const eps = subject?.eps || 'N/A';
          
          // 获取进度 (仅针对收藏条目)
          const watchedEp = item.ep_status || 0;
          const isCollection = !!item.ep_status; // 判断是否是收藏记录

          // 获取放送日期
          const airDate = subject?.date || '未知日期';
          
          // 解析制作公司 (从 infobox 查找 key 为 '动画制作' 或 '开发' 的项)
          // 注意：infobox 可能是 JSON 字符串或对象，视后端返回而定，这里假设是对象数组
          const studioInfo = subject?.infobox?.find((i: any) => 
            ['动画制作', '开发', '作者'].includes(i.key)
          );
          const studio = studioInfo?.value || '未知制作';

          const tags = (subject?.tags || []).slice(0, 3).map((tag: any) => tag.name);

          // --- 处理函数 ---
          const handleSearch = (e: React.MouseEvent) => {
            e.stopPropagation(); // 阻止冒泡，防止触发卡片点击
            
            // 优先使用 title 变量（它在上面定义过：优先取 name_cn 中文名，其次取 name）
            // 如果 title 为空，再兜底试一下 subject?.name
            const searchKeyword = title || subject?.name;

            if (searchKeyword) {
                window.open(`https://search.bilibili.com/all?keyword=${encodeURIComponent(searchKeyword)}`, '_blank');
            }
          };

          const handleRSS = (e: React.MouseEvent) => {
            e.stopPropagation();
            console.log('触发 RSS 订阅逻辑', subject?.id);
            
            // 获取中文名称
            const name_cn = subject?.name_cn || subject?.name || item.title;
            
            // 构建 comicat 搜索 RSS URL（国内友好）
            const rssUrlTemplate = process.env.NEXT_PUBLIC_RSS_URL_TEMPLATE || 'https://comicat.org/rss-%s.xml';
            const rssUrl = rssUrlTemplate.replace('%s', encodeURIComponent(name_cn));
            
            setSelectedItem({ ...item, name_cn, rssUrl });
            setIsSubscriptionModalOpen(true);
          };

          return (
            // 给最外层加 group，用于 hover 控制
            <div 
              className={`group flex flex-col h-full ${isDarkMode ? 'dark:bg-slate-800' : 'bg-white'} h-full overflow-hidden cursor-pointer`}
              onClick={() => onOpenDetail?.(item)} // 点击卡片主体打开 Modal
            >
              
              {/* --- 封面区域 (Relative定位基准点) --- */}
              <div className={`aspect-[2/3] w-full relative ${isDarkMode ? 'dark:bg-slate-900' : 'bg-slate-100'} overflow-hidden`}>
                {cover ? (
                  <img 
                    key={cover} 
                    src={cover} 
                    alt={title} 
                    referrerPolicy="no-referrer"
                    // hover 时稍微放大一点图片，增加动感
                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                ) : (
                  <div className={`w-full h-full flex items-center justify-center ${isDarkMode ? 'text-slate-600' : 'text-slate-300'}`}>No Image</div>
                )}
                
                {/* 评分角标 (移到左上角) */}
                {score && (
                  <div className="absolute top-2 left-2 bg-black/60 backdrop-blur-md text-white text-xs font-bold px-1.5 py-0.5 rounded flex items-center gap-1 shadow-sm z-20">
                    <span className="text-yellow-400">★</span>{score}
                  </div>
                )}

                {/* 🔥🔥🔥 核心实现：侧边极简工具栏 (Mini Side Bar) 🔥🔥🔥 */}
                <div className={`absolute top-0 right-0 bottom-0 z-10 w-11
                                flex flex-col items-center justify-center gap-3 py-3
                                ${isDarkMode ? 'bg-slate-900/70 backdrop-blur-sm border-l border-white/10' : 'bg-white/60 backdrop-blur-sm border-l border-black/10'}
                                transform-gpu will-change-transform transform translate-x-full group-hover:translate-x-0 
                                transition-transform duration-300 cubic-bezier(0.2, 0, 0, 1)`}>

                  {/* 2. B站搜索 */}
                  <ActionIcon
                    icon={BilibiliIcon}
                    title="B站搜索"
                    glass
                    size="middle"
                    onClick={handleSearch}
                    variant="outlined"
                    style={{ color: isDarkMode ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)' }}
                  />

                  {/* 3. 订阅 RSS */}
                  <ActionIcon
                    icon={Rss}
                    title="RSS 订阅"
                    glass
                    size="middle"
                    onClick={handleRSS}
                    variant="outlined"
                    style={{ color: isDarkMode ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)' }}
                  />

                  {/* 4. 更多/详情 (底部) */}
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
                {/* 🔥🔥🔥 滑出层结束 🔥🔥🔥 */}

              </div>
              
              {/* 信息区域 */}
              <div className={`p-3 flex flex-col flex-1 gap-2 relative ${isDarkMode ? 'bg-slate-800' : 'bg-white'} z-20`}>
                <h3 className={`font-medium text-sm ${isDarkMode ? 'text-slate-100' : 'text-slate-900'} line-clamp-2 leading-tight`} title={title}>
                  {title || '无标题'}
                </h3>
                <div className="mt-auto flex items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-1">
                    {tags.map((tag: string, index: number) => (
                      <Tag key={index} size="small" style={{ opacity: 0.8, fontSize: '10px', height: '20px' }}>
                        {tag}
                      </Tag>
                    ))}
                  </div>
                  <span className={`text-xs ${isDarkMode ? 'text-slate-400' : 'text-slate-400'} font-mono whitespace-nowrap`}>
                    {eps !== 'N/A' ? `${eps}集` : ''}
                  </span>
                </div>
              </div>
            </div>
          );
        }}
      />

      {/* 智能订阅模态框 */}
      <SmartSubscriptionModal
        open={isSubscriptionModalOpen}
        onClose={() => {
          setIsSubscriptionModalOpen(false);
          setSelectedItem(null);
        }}
        onSubmit={(data) => {
          console.log('订阅数据:', data);
          // 这里可以添加保存订阅的逻辑
        }}
        initialValues={{
          rssUrl: selectedItem?.rssUrl,
          name: selectedItem?.name_cn
        }}
      />
    </div>
  );
}