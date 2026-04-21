import React, { useState, useEffect } from 'react';
import { Modal, Button, Icon, toast } from '@lobehub/ui';
import { Rss, ExternalLink, CheckCircle2, XCircle, Globe } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';
import SubjectForm from './form/SubjectForm';
import SmartSubscriptionModal from './SmartSubscriptionModal';
import { FormData } from './types';
import { collectionService } from '@/services/collections';

interface SubjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialValues?: Partial<FormData>;
}

const SubjectModal = ({ isOpen, onClose, initialValues }: SubjectModalProps) => {
  const { isDarkMode } = useAppTheme();
  const [loading, setLoading] = useState(false);
  const [isSubscriptionModalOpen, setIsSubscriptionModalOpen] = useState(false);
  const [subscriptionData, setSubscriptionData] = useState<any>(null);
  
  // 解析项目数据的函数
  const parseItemData = (item: any): FormData => {
    if (!item) {
      // 默认空表单数据
      return {
        title: '',
        subject: {
          id: 0,
          date: '',
          images: {
            small: '',
            grid: '',
            large: '',
            medium: '',
            common: ''
          },
          name: '',
          name_cn: '',
          short_summary: '',
          tags: [],
          score: 0,
          type: 0,
          eps: 0,
          volumes: 0,
          source: ''
        },
        cover: '',
        collectionType: 1, // 默认值为"想看"
        rate: 0,
        comment: '',
        volStatus: 0,
        epStatus: 0,
        tags: ''
      };
    }
    
    // 提取 subject 和 collection 数据
    const subject = item.subject || item;
    const collection = item.collection || {};
    
    // 构建表单数据
    return {
      title: String(subject.name_cn || subject.name || item.title || ''),
      subject: {
        id: Number(subject.id || subject.source_id || 0),
        date: String(subject.date || ''),
        images: subject.images || {
          small: '',
          grid: '',
          large: subject.image || '',
          medium: '',
          common: subject.image || ''
        },
        name: String(subject.name || ''),
        name_cn: String(subject.name_cn || ''),
        short_summary: String(subject.short_summary || subject.summary || ''),
        tags: subject.tags || [],
        score: Number(subject.rating?.score || subject.score || 0),
        type: Number(subject.type || subject.subject_type || 0),
        eps: Number(subject.eps || 0),
        volumes: Number(subject.volumes || 0),
        source: String(subject.source || '')
      },
      cover: String(subject.images?.large || subject.images?.medium || subject.image || ''),
      collectionType: Number(collection.type || item.type || 1), // 默认值为"想看"
      rate: Number(collection.rate || item.rate || 0),
      comment: String(collection.comment || item.comment || ''),
      volStatus: Number(collection.vol_status || item.vol_status || 0),
      epStatus: Number(collection.ep_status || item.ep_status || 0),
      tags: String(collection.tags || item.tags || '')
    };
  };
  
  // 当 initialValues 变化时，更新 formData
  const [formData, setFormData] = useState<FormData>(() => {
    return parseItemData(initialValues);
  });
  
  // 当 initialValues 变化时，更新 formData
  useEffect(() => {
    if (!initialValues) return;
    
    const parsedData = parseItemData(initialValues);
    setFormData(parsedData);
  }, [initialValues]);

  const handleOk = async () => {
    try {
      setLoading(true);

      // 构建请求数据
      const requestData = {
        data: [{
          subject: formData.subject,
          collection: {
            type: formData.collectionType || 2, // 默认值为"看过"
            rate: formData.rate,
            comment: formData.comment,
            vol_status: formData.volStatus,
            ep_status: formData.epStatus,
            tags: formData.tags
          }
        }]
      };

      // 调用后端 API
      const result = await collectionService.uploadDouban(requestData);

      // 显示成功通知
      toast.success({
        title: '上传成功',
        description: `成功导入 ${result.sync_count} 条数据`,
        icon: CheckCircle2,
        duration: 3000,
      });

      // 关闭模态框
      onClose();
    } catch (error) {
      console.error('Upload error:', error);
      // 显示错误通知
      toast.error({
        title: '上传失败',
        description: error instanceof Error ? error.message : '上传失败，请重试',
        icon: XCircle,
        duration: 3000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRssSubscribe = () => {
    const name_cn = formData.subject?.name_cn || formData.subject?.name || formData.title;
    if (!name_cn) {
      toast.error({
        title: '错误',
        description: '请先填写条目名称',
        icon: XCircle,
        duration: 3000,
      });
      return;
    }
    
    // 构建 comicat 搜索 RSS URL（国内友好）
    const rssUrlTemplate = process.env.NEXT_PUBLIC_RSS_URL_TEMPLATE || 'https://comicat.org/rss-%s.xml';
    const rssUrl = rssUrlTemplate.replace('%s', encodeURIComponent(name_cn));
    
    // 设置订阅数据并打开模态框
    setSubscriptionData({ name: name_cn, rssUrl });
    setIsSubscriptionModalOpen(true);
  };

  const handleBilibiliRedirect = () => {
    const name_cn = formData.subject?.name_cn || formData.subject?.name || formData.title;
    if (!name_cn) {
      toast.error({
        title: '错误',
        description: '请先填写条目名称',
        icon: XCircle,
        duration: 3000,
      });
      return;
    }
    
    // 构建 B 站搜索 URL
    const bilibiliUrl = `https://search.bilibili.com/all?keyword=${encodeURIComponent(name_cn)}`;
    
    // 打开新窗口
    window.open(bilibiliUrl, '_blank');
  };

  const handleBangumiRedirect = () => {
    const subjectId = formData.subject?.id;
    if (!subjectId || subjectId === 0) {
      toast.error({
        title: '错误',
        description: '条目ID无效，无法跳转到Bangumi',
        icon: XCircle,
        duration: 3000,
      });
      return;
    }
    
    // 构建 Bangumi 网站链接
    const bangumiUrl = `https://bangumi.tv/subject/${subjectId}`;
    
    // 打开新窗口
    window.open(bangumiUrl, '_blank');
  };

  return (
    <>
      <Modal
        open={isOpen}
        title="条目详情"
        onCancel={onClose}
        onOk={handleOk}
        okText={loading ? "处理中..." : "更新/上传"}
        cancelText="取消"
        centered
        width={700}
        okButtonProps={{ loading }}
        destroyOnHidden
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 主体表单 */}
          <SubjectForm value={formData} onChange={setFormData} />
          
          {/* 底部按钮区域 */}
          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            <Button 
              type="default" 
              icon={<Icon icon={Rss} />}
              onClick={handleRssSubscribe}
              style={{ flex: 1 }}
            >
              RSS 订阅
            </Button>
            <Button 
              type="default" 
              icon={<Icon icon={ExternalLink} />}
              onClick={handleBilibiliRedirect}
              style={{ flex: 1 }}
            >
              B 站跳转
            </Button>
            <Button 
              type="default" 
              icon={<Icon icon={Globe} />}
              onClick={handleBangumiRedirect}
              style={{ flex: 1 }}
            >
              Bangumi
            </Button>
          </div>
        </div>
      </Modal>
      
      {/* 智能订阅模态框 */}
      <SmartSubscriptionModal
        open={isSubscriptionModalOpen}
        onClose={() => {
          setIsSubscriptionModalOpen(false);
          setSubscriptionData(null);
        }}
        onSubmit={(data) => {
          console.log('订阅数据:', data);
          // 订阅成功后关闭模态框
          setIsSubscriptionModalOpen(false);
          setSubscriptionData(null);
        }}
        initialValues={subscriptionData}
      />
    </>
  );
};

export default SubjectModal;