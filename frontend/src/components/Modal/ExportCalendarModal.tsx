import React from 'react';
import { Modal, Button, Divider, Typography } from 'antd';
import { Download, Volume2 } from 'lucide-react';
import { Highlighter } from '@lobehub/ui';
import { downloadCSV } from '../../services/CalendarService';

const { Text, Paragraph } = Typography;

interface ExportCalendarModalProps {
  open: boolean;
  onCancel: () => void;
  subjectName: string;
  csvString: string;
  voiceCommand: string;
}

export const ExportCalendarModal: React.FC<ExportCalendarModalProps> = ({
  open,
  onCancel,
  subjectName,
  csvString,
  voiceCommand,
}) => {
  
  const handleDownloadCSV = () => {
    downloadCSV(csvString, `${subjectName}_日历订阅`);
  };

  return (
    <Modal
      title="导出追番日程"
      open={open}
      onCancel={onCancel}
      footer={null}
      width={480}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '24px' }}>
        
        <div>
          <Text strong>1. 导入日历应用 (CSV格式)</Text>
          <Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 12 }}>
            适用于 Google Calendar、Outlook 或 Apple 日历。下载后在日历设置中选择导入即可。
          </Paragraph>
          <Button
            type="primary"
            icon={<Download size={16} />}
            onClick={handleDownloadCSV}
            block
          >
            下载日历 CSV 文件
          </Button>
        </div>

        <Divider style={{ margin: '8px 0' }} />

        <div>
          <Text strong>
            2. 语音助手快捷指令
          </Text>
          <Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 12 }}>
            唤醒手机语音助手（如 Siri、小爱同学），将下方文本直接粘贴发送。
          </Paragraph>
          
          <div style={{ marginTop: '12px' }}>
            <Highlighter
              language="text"      // 纯文本模式，不需要语法高亮
              copyable={true}      // 开启一键复制按钮
              showLanguage={false} // 隐藏右上角的 "text" 标签，让它看起来更像普通提示框
              style={{
                minHeight: '120px',             // 保证基础高度
                maxHeight: '240px',             // 限制最大高度
                overflowY: 'auto',              // 超出后允许纵向滚动
                whiteSpace: 'pre-wrap',         // 确保长文本自动换行
                wordBreak: 'break-word',
                border: '1px solid var(--lobe-color-border)' // 可选：加上边框增加层次感
              }}
            >
              {voiceCommand}
            </Highlighter>
          </div>
        </div>
      </div>
    </Modal>
  );
};