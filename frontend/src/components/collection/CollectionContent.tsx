import { Empty, Tag } from '@lobehub/ui';
import { SpotlightCard } from '@lobehub/ui/awesome';

interface CollectionContentProps {
  items: any[]; 
}

export default function CollectionContent({ items = [] }: CollectionContentProps) {
  // 1. 空状态处理
  if (!items || items.length === 0) {
    return <Empty description="暂无内容" image="simple" />;
  }

  return (
    <div className="p-4">
      {/* 🔥 核心修正：
        1. SpotlightCard 本身就是容器，不要在外面包 Grid
        2. 把 items 传给它
        3. 用 renderItem 定义每一项长什么样
      */}
      <SpotlightCard
        items={items}
        // 类似于 Grid 的 gap
        gap={20}
        // 类似于 Grid width={180}，自适应宽度
        maxItemWidth={180}
        // 卡片圆角
        borderRadius={12}

        columns={5}
        
        renderItem={(item) => {
          // --- ⬇️ 数据清洗逻辑 (搬到这里面) ⬇️ ---
          const isSubject = !!item.subject;
          
          const title = isSubject 
            ? (item.subject?.name_cn || item.subject?.name) 
            : item.title;
            
          const cover = isSubject 
            ? item.subject?.images?.large 
            : item.cover;
            
          const score = isSubject 
            ? item.subject?.score 
            : item.score;
            
          // 类型处理
          let typeText = '未知';
          if (isSubject) {
             typeText = item.subject?.type === 2 ? 'TV' : 'Movie';
          } else {
             typeText = item.type === 'anime' ? 'TV' 
                      : item.type === 'movie' ? 'Movie' 
                      : item.type === 'manga' ? 'Manga'
                      : item.type;
          }

          const eps = isSubject ? item.subject?.eps : (item.eps || 'N/A');

          // --- ⬇️ 返回卡片内部的内容 ⬇️ ---
          return (
            <div className="flex flex-col h-full bg-white dark:bg-slate-800 h-full overflow-hidden">
              {/* 封面区域 */}
              <div className="aspect-[2/3] w-full relative bg-slate-100 dark:bg-slate-900 overflow-hidden">
                {cover ? (
                  <img 
                    // 🔥🔥🔥 核心修复：加上这行 key！
                    // 告诉 React：如果封面地址变了，这是一个全新的 img，不要复用旧的
                    key={cover} 
                    
                    src={cover} 
                    alt={title} 
                    referrerPolicy="no-referrer"
                    className="w-full h-full object-cover transition-transform duration-500 hover:scale-110"
                    />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-300">
                    No Image
                  </div>
                )}
                
                {/* 评分角标 */}
                {score && (
                  <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-xs font-bold px-1.5 py-0.5 rounded flex items-center gap-1 shadow-sm">
                    <span className="text-yellow-400">★</span>{score}
                  </div>
                )}
              </div>
              
              {/* 信息区域 */}
              <div className="p-3 flex flex-col flex-1 gap-2">
                <h3 className="font-medium text-sm text-slate-900 dark:text-slate-100 line-clamp-2 leading-tight" title={title}>
                  {title || '无标题'}
                </h3>
                
                <div className="mt-auto flex items-center justify-between">
                  <Tag size="small" style={{ opacity: 0.8 }}>
                    {typeof typeText === 'string' ? typeText.toUpperCase() : typeText}
                  </Tag>
                  <span className="text-xs text-slate-400 font-mono">
                    {eps !== 'N/A' ? `${eps}集` : ''}
                  </span>
                </div>
              </div>
            </div>
          );
        }}
      />
    </div>
  );
}