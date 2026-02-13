import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Collapse, Switch, Button, Select, Space, Card, AutoComplete, Tag, Alert } from 'antd';
import { Wand2, FolderOpen, Rss, Link, Save, CheckCircle2, AlertCircle } from 'lucide-react';
import { toast } from '@lobehub/ui';
import { Icon } from '@lobehub/ui';
import { MessageModal } from '@lobehub/ui/chat';
import { getRssRules, upsertRssFeed, setRssRule } from '@/services/rss'; 
import { RssRule, AddRssFeedRequest, SetRssRuleRequest, TorrentParams } from './types';

const { Panel } = Collapse;

// 定义表单字段
interface SmartSubscriptionFormValues {
  rssUrl: string;
  feedName: string;
  ruleName: string; 
  mustContain?: string;
  mustNotContain?: string;
  savePath?: string;
  category?: string[]; // 注意：Select mode="tags" 返回的是字符串数组
  tags?: string[];
  useRegex?: boolean;
  smartFilter?: boolean;
  priority?: number;
}

const SmartSubscriptionModal = ({ 
  open, 
  onClose, 
  onSubmit, 
  initialValues 
}: { 
  open: boolean; 
  onClose: () => void; 
  onSubmit?: (data: any) => void; 
  initialValues?: any 
}) => {
  const [form] = Form.useForm();
  
  // 监听表单中的 ruleName 变化
  const currentRuleName = Form.useWatch('ruleName', form);
  
  const [isSmartParsing, setIsSmartParsing] = useState(false);
  
  // 现有规则数据
  const [existingRulesData, setExistingRulesData] = useState<Record<string, RssRule>>({});
  const [ruleOptions, setRuleOptions] = useState<Array<{ value: string; label: string }>>([]);
  
  // 计算当前输入的规则名是否已存在 (用于显示提示，不再用于隐藏表单)
  const isExistingRule = !!(currentRuleName && existingRulesData[currentRuleName]);

  // AI Modal
  const [messageModalOpen, setMessageModalOpen] = useState(false);
  const [messageModalValue, setMessageModalValue] = useState('');

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({
        useRegex: true,
        smartFilter: true,
        priority: 0,
        feedName: initialValues?.name,
        ...initialValues,
      });
      fetchRules();
    }
  }, [open, initialValues, form]);

  // 新增：监听规则名称变化，实现自动回填逻辑
  useEffect(() => {
    // 如果当前输入的名称在现有规则库中
    if (currentRuleName && existingRulesData[currentRuleName]) {
      const targetRule = existingRulesData[currentRuleName];
      
      // 回填数据到表单
      form.setFieldsValue({
        mustContain: targetRule.mustContain,
        mustNotContain: targetRule.mustNotContain,
        savePath: targetRule.savePath,
        // 处理分类：如果是字符串需要转为数组以适配 Select mode="tags"
        category: targetRule.assignedCategory ? [targetRule.assignedCategory] : [],
        useRegex: targetRule.useRegex,
        smartFilter: targetRule.smartFilter,
        priority: targetRule.priority,
      });
      
      // 可选：如果不希望用户不知道发生了什么，可以给个轻提示，或者完全静默
    }
  }, [currentRuleName, existingRulesData, form]);

  const fetchRules = async () => {
    try {
      const response = await getRssRules();
      setExistingRulesData(response.rules);
      const options = Object.keys(response.rules).map((key) => ({
        value: key,
        label: key,
      }));
      setRuleOptions(options);
    } catch (error) {
      console.error('Failed to fetch rules', error);
    }
  };

  const handleSmartFillStart = () => {
    const url = form.getFieldValue('rssUrl');
    if (!url) {
      toast.error({ title: '请先填写 RSS 链接', description: 'AI 需要链接来抓取样本' });
      return;
    }
    setMessageModalValue('点击发送，开始智能分析...');
    setMessageModalOpen(true);
  };

  const handleSmartFillProcess = async () => {
    setMessageModalValue('AI 正在分析...');
    setIsSmartParsing(true);
    
    setTimeout(() => {
      const aiResult = {
        feedName: '迷宫饭 (Dungeon Meshi)', 
        ruleName: '迷宫饭 Auto', 
        mustContain: '迷宫饭.*1080p',
        mustNotContain: '720p|合集',
        savePath: '/downloads/Anime/2024/迷宫饭',
        category: ['Anime'], // 修正为数组
        useRegex: true
      };

      form.setFieldsValue(aiResult);
      setIsSmartParsing(false);
      setMessageModalOpen(false);
      toast.success({ title: '智能填充完成', description: '请确认规则配置' });
    }, 1200);
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields() as SmartSubscriptionFormValues;
      const { feedName, rssUrl, ruleName } = values;

      // 1. 添加 Feed
      await upsertRssFeed({ url: rssUrl, name: feedName });

      // 2. 处理规则
      let finalRuleBody: RssRule;
      const targetExistingRule = existingRulesData[ruleName];

      // 处理 category 字段，将数组转回字符串
      const assignedCategoryStr = Array.isArray(values.category) && values.category.length > 0 
        ? values.category[0] 
        : (values.category as any as string) || '';

      if (targetExistingRule) {
        // === 情况 A: 规则已存在 (更新) ===
        // 更新规则，包括用户在表单上修改的所有参数
        const currentFeeds = targetExistingRule.affectedFeeds || [];
        const newFeeds = currentFeeds.includes(rssUrl) ? currentFeeds : [...currentFeeds, rssUrl];
        
        finalRuleBody = {
          ...targetExistingRule,
          affectedFeeds: newFeeds,
          mustContain: values.mustContain || '',
          mustNotContain: values.mustNotContain || '',
          savePath: values.savePath || '',
          assignedCategory: assignedCategoryStr,
          useRegex: values.useRegex || false,
          smartFilter: values.smartFilter || true,
          priority: values.priority || 0,
          torrentParams: {
            category: assignedCategoryStr,
            content_layout: targetExistingRule.torrentParams?.content_layout,
            download_limit: targetExistingRule.torrentParams?.download_limit || 0,
            download_path: targetExistingRule.torrentParams?.download_path || '',
            inactive_seeding_time_limit: targetExistingRule.torrentParams?.inactive_seeding_time_limit || -2,
            operating_mode: targetExistingRule.torrentParams?.operating_mode || 'AutoManaged',
            ratio_limit: targetExistingRule.torrentParams?.ratio_limit || -2,
            save_path: values.savePath || '',
            seeding_time_limit: targetExistingRule.torrentParams?.seeding_time_limit || -2,
            share_limit_action: targetExistingRule.torrentParams?.share_limit_action || 'Default',
            skip_checking: targetExistingRule.torrentParams?.skip_checking || false,
            ssl_certificate: targetExistingRule.torrentParams?.ssl_certificate || '',
            ssl_dh_params: targetExistingRule.torrentParams?.ssl_dh_params || '',
            ssl_private_key: targetExistingRule.torrentParams?.ssl_private_key || '',
            tags: values.tags || [],
            upload_limit: targetExistingRule.torrentParams?.upload_limit || 0,
            use_auto_tmm: targetExistingRule.torrentParams?.use_auto_tmm,
            stop_condition: targetExistingRule.torrentParams?.stop_condition
          }
        };
      } else {
        // === 情况 B: 规则不存在 (新建) ===
        finalRuleBody = {
          enabled: true,
          affectedFeeds: [rssUrl],
          mustContain: values.mustContain || '',
          mustNotContain: values.mustNotContain || '',
          savePath: values.savePath || '',
          assignedCategory: assignedCategoryStr,
          useRegex: values.useRegex || false,
          smartFilter: values.smartFilter || true,
          priority: values.priority || 0,
          ignoreDays: 0,
          previouslyMatchedEpisodes: [],
          episodeFilter: '',
          torrentParams: {
             save_path: values.savePath || '',
             category: assignedCategoryStr,
             tags: values.tags || [],
             download_limit: 0, upload_limit: 0, 
             operating_mode: 'AutoManaged', inactive_seeding_time_limit: -2, 
             ratio_limit: -2, seeding_time_limit: -2, share_limit_action: 'Default', 
             skip_checking: false, ssl_certificate: '', ssl_dh_params: '', ssl_private_key: '', 
             download_path: '', use_auto_tmm: false
          }
        };
      }

      await setRssRule({ rule_name: ruleName, rule: finalRuleBody });
      toast.success({ 
        title: '操作成功', 
        description: targetExistingRule ? `已合并至现有规则 "${ruleName}"` : `已新建规则 "${ruleName}"` 
      });
      onSubmit?.(values);
      onClose();

    } catch (error: any) {
      console.error(error);
      toast.error({ title: '失败', description: error.message });
    }
  };

  return (
    <>
      <Modal
        title={<Space><Icon icon={Rss} className="text-primary"/><span>添加 RSS 订阅</span></Space>}
        open={open}
        onCancel={onClose}
        onOk={handleOk}
        width={680}
        destroyOnClose
        maskClosable={false}
      >
        <Form form={form} layout="vertical">
          
          {/* === 基础信息 === */}
          <div className="bg-gray-50/50 p-4 rounded-lg border border-gray-100 mb-5">
            <Form.Item label="RSS 链接" name="rssUrl" rules={[{ required: true }]} style={{marginBottom: 12}}>
              <Input 
                placeholder="粘贴 RSS 地址..." 
                suffix={
                  <Button type="text" size="small" icon={<Icon icon={Wand2} className="text-purple-500" />} 
                    loading={isSmartParsing} onClick={handleSmartFillStart}>
                    AI 识别
                  </Button>
                }
              />
            </Form.Item>
            <Form.Item label="订阅源名称 (Feed Name)" name="feedName" rules={[{ required: true }]} style={{marginBottom: 0}}>
              <Input placeholder="RSS 在列表中的显示名称" />
            </Form.Item>
          </div>

          <div className="relative">
            <div className="absolute inset-0 flex items-center" aria-hidden="true">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-white px-2 text-sm text-gray-500 flex items-center gap-1">
                <Icon icon={Save} size={14}/> 下载规则设置
              </span>
            </div>
          </div>

          {/* === 统一的规则名称输入 === */}
          <div className="mt-5 mb-1">
             <Form.Item 
                name="ruleName" 
                label="下载规则名称" 
                tooltip="输入新名称以创建规则，或从下拉菜单选择现有规则。选择现有规则将自动填充其配置。"
                rules={[{ required: true, message: '请指定一个规则' }]}
              >
                <AutoComplete
                  options={ruleOptions}
                  placeholder="输入名称或选择现有规则..."
                  filterOption={(inputValue, option) =>
                    option!.value.toUpperCase().indexOf(inputValue.toUpperCase()) !== -1
                  }
                />
              </Form.Item>
          </div>

         {/* === 动态内容区域 === */}
          {/* 移除 min-h-[200px] 以避免内容较少时出现不必要的留白，移除负 margin */}
          <div className="animate-in fade-in slide-in-from-top-2 duration-300">
            
            {/* 提示条区域：统一使用 Alert 组件以保证字体和间距一致 */}
            <div className="mb-5">
              {isExistingRule ? (
                <Alert
                  message="将使用现有规则"
                  type="info"
                  showIcon
                  closable
                  // 移除所有内联 style，Ant Design 默认字体即与表单一致
                />
              ) : (
                currentRuleName && (
                  <Alert
                    message={
                      <span>
                        将创建新规则: <strong>{currentRuleName}</strong>
                      </span>
                    }
                    type="success" // 使用 success 类型替代手写的绿色 div
                    showIcon
                  />
                )
              )}
            </div>
            
            {/* 表单字段区域 - 不再根据 isExistingRule 隐藏 */}
            <div className="grid grid-cols-2 gap-4">
              <Form.Item label="必须包含 (正则/关键词)" name="mustContain">
                <Input placeholder="例如：1080p|CHS" />
              </Form.Item>
              <Form.Item label="保存路径" name="savePath">
                <Input prefix={<Icon icon={FolderOpen} size={14}/>} />
              </Form.Item>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Form.Item label="分类" name="category">
                <Select options={[{ label: 'Anime', value: 'Anime' }]} mode="tags" />
              </Form.Item>
              <Form.Item label="必须不含" name="mustNotContain">
                <Input placeholder="例如：720p" />
              </Form.Item>
            </div>

            <Collapse ghost size="small">
              <Panel header={<span className="text-xs text-gray-500">高级选项</span>} key="1">
                <Space size="large" className="mt-2">
                  <Form.Item name="useRegex" valuePropName="checked" label="正则模式" layout="horizontal" style={{marginBottom:0}}>
                    <Switch size="small" />
                  </Form.Item>
                  <Form.Item name="smartFilter" valuePropName="checked" label="智能剧集过滤" layout="horizontal" style={{marginBottom:0}}>
                    <Switch size="small" />
                  </Form.Item>
                </Space>
              </Panel>
            </Collapse>
          </div>
        </Form>
      </Modal>

      <MessageModal
        open={messageModalOpen}
        onOpenChange={setMessageModalOpen}
        editing={false}
        value={messageModalValue}
        onChange={setMessageModalValue}
      />
    </>
  );
};

export default SmartSubscriptionModal;