import { Empty } from '@lobehub/ui';
import { SpotlightCard } from '@lobehub/ui/awesome';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { useState } from 'react';
import SmartSubscriptionModal from '@/components/Modal/SmartSubscriptionModal';
import SubjectModal from '@/components/Modal/SubjectModal';
import MediaCard from './MediaCard';



interface CollectionContentProps {
  items: any[];
  onOpenDetail?: (item: any) => void; // 假设你有个点击打开详情的回调
}

export default function CollectionContent({ items = [], onOpenDetail }: CollectionContentProps) {
  const { isDarkMode } = useAppTheme();
  const [isSubscriptionModalOpen, setIsSubscriptionModalOpen] = useState(false);
  const [isSubjectModalOpen, setIsSubjectModalOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<any>(null);
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
    onOpenDetail?.(formattedItem);
  };
  
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
          const handleRSS = (data: any) => {
            // 获取中文名称
            const subject = data.subject || data;
            const name_cn = subject?.name_cn || subject?.name || data.title;
            
            // 构建 comicat 搜索 RSS URL（国内友好）
            const rssUrlTemplate = process.env.NEXT_PUBLIC_RSS_URL_TEMPLATE || 'https://comicat.org/rss-%s.xml';
            const rssUrl = rssUrlTemplate.replace('%s', encodeURIComponent(name_cn));
            
            setSelectedItem({ ...data, name_cn, rssUrl });
            setIsSubscriptionModalOpen(true);
          };

          return (
            <MediaCard
              data={item}
              variant="large"
              onOpenDetail={handleOpenDetail}
              onRSS={handleRSS}
            />
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

      {/* 条目详情模态框 */}
      <SubjectModal
        isOpen={isSubjectModalOpen}
        onClose={() => {
          setIsSubjectModalOpen(false);
          setSelectedSubject(null);
        }}
        initialValues={selectedSubject}
      />
    </div>
  );
}