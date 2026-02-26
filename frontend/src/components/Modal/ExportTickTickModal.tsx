import React, { useState, useMemo } from 'react';
import { Modal, Typography, Input, Select, Space } from 'antd';
import { CheckSquare } from 'lucide-react';
import { Highlighter } from '@lobehub/ui';
// 确保路径正确指向你的 Service 和 Type 文件
import { generateAllTickTickCommands } from '../../services/CalendarService';
import { BangumiItem } from '../../services/bangumiService'; 

const { Text, Paragraph } = Typography;

interface ExportTickTickModalProps {
  open: boolean;
  onCancel: () => void;
  items: BangumiItem[]; // 修改点：接收数组
}

export const ExportTickTickModal: React.FC<ExportTickTickModalProps> = ({
  open,
  onCancel,
  items,
}) => {
  // 滴答清单定制化配置状态
  const [tickList, setTickList] = useState<string>('追番');
  const [tickPriority, setTickPriority] = useState<string>('无');
  const [tickTags, setTickTags] = useState<string[]>(['动画']);

  // 修改点：实时生成所有项目的指令
  const ticktickCommand = useMemo(() => {
    return generateAllTickTickCommands(items, {
      listName: tickList,
      priority: tickPriority,
      tags: tickTags,
    });
  }, [items, tickList, tickPriority, tickTags]);

  return (
    <Modal
      title="全量导出到滴答清单"
      open={open}
      onCancel={onCancel}
      footer={null}
      width={700} // 批量导出内容较多，加宽一点
      destroyOnClose
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
        
        <div>
          <Paragraph type="secondary" style={{ marginBottom: 16 }}>
            配置下方任务属性，一键复制并在滴答清单中粘贴，选择<b>“创建多个任务”</b>，即可自动识别追番日期与所有属性。
          </Paragraph>

          {/* 定制化配置面板 */}
          <div style={{ 
            padding: '16px', 
            backgroundColor: 'var(--lobe-color-fill-tertiary, rgba(0,0,0,0.02))', 
            borderRadius: '8px',
            marginBottom: '16px',
            border: '1px solid var(--lobe-color-border)'
          }}>
            <Space size="large" wrap style={{ width: '100%' }}>
              <div>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>加入清单，如有emoji也需要输入</Text>
                <Input 
                  placeholder="例如：😀追番" 
                  value={tickList} 
                  onChange={(e) => setTickList(e.target.value)}
                  style={{ width: 140 }}
                  allowClear
                />
              </div>
              
              <div>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>优先级</Text>
                <Select
                  value={tickPriority}
                  onChange={setTickPriority}
                  style={{ width: 100 }}
                  options={[
                    { value: '无', label: '无' },
                    { value: '高优先级', label: '高优先级' },
                    { value: '中优先级', label: '中优先级' },
                    { value: '低优先级', label: '低优先级' },
                  ]}
                />
              </div>

              <div style={{ flex: 1, minWidth: '200px' }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>添加标签 (输入后回车)</Text>
                <Select
                  mode="tags"
                  style={{ width: '100%' }}
                  placeholder="输入标签"
                  value={tickTags}
                  onChange={setTickTags}
                  options={[
                    { value: '动画', label: '动画' },
                    { value: '新番', label: '新番' },
                    { value: '补番', label: '补番' },
                  ]}
                />
              </div>
            </Space>
          </div>
          
          {/* 实时预览的高亮文本框，使用 LobeHub UI */}
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            生成结果 (共 {items.length} 部番剧，点击右上角复制)：
          </Text>
          <Highlighter
            language="text"
            copyable
            showLanguage={false}
            style={{
              minHeight: '200px', // 批量导出增加初始高度
              maxHeight: '450px',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              border: '1px solid var(--lobe-color-border)'
            }}
          >
            {ticktickCommand}
          </Highlighter>
        </div>

      </div>
    </Modal>
  );
};