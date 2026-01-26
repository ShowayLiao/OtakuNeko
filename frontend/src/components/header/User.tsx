import { Avatar, Button, Flexbox, Popover, Tag } from '@lobehub/ui';
import { createStaticStyles } from 'antd-style';
import {
  BarChart2,
  ChevronDown,
  CreditCard,
  Download,
  LogOut,
  MessageSquare,
  Settings,
  Sparkles,
} from 'lucide-react';
import type React from 'react';

const MenuItem = ({ icon: Icon, children }: { children: string; icon: React.ElementType }) => (
  <Button
    block
    icon={<Icon size={16} />}
    style={{
      justifyContent: 'flex-start',
      padding: '10px 16px',
      transition: 'all 0.2s',
    }}
    type="text"
  >
    {children}
  </Button>
);

const StatItem = ({
  icon: Icon,
  label,
  value,
  color,
}: {
  color: string;
  icon: React.ElementType;
  label: string;
  value: number;
}) => (
  <Flexbox
    gap={8}
    style={{
      background: 'var(--lobe-color-fill-tertiary)',
      borderRadius: 10,
      flex: 1,
      padding: '12px 14px',
      transition: 'all 0.2s',
    }}
  >
    <Flexbox align="center" gap={8} horizontal>
      <Icon size={16} style={{ color }} />
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
    </Flexbox>
    <div style={{ color: 'var(--lobe-color-text-3)', fontSize: 12, fontWeight: 500 }}>
      {label}
    </div>
  </Flexbox>
);

const styles = createStaticStyles(({ css }) => ({
  content: css`
    padding: 8px;
  `,
}));

const User: React.FC = () => {
  const avatarUrl = 'https://cdn.jsdelivr.net/gh/Innei/static@master/avatar.png';

  return (
    <Flexbox align="center" justify="flex-start" style={{ padding: 0 }}>
      <Popover
        arrow={false}
        classNames={{
          content: styles.content,
        }}
        content={
          <Flexbox gap={12} style={{ width: 360 }}>
            {/* User Info Section with gradient background */}
            <Flexbox align="center" gap={14} horizontal style={{
                background: 'linear-gradient(135deg, var(--lobe-color-fill-secondary) 0%, var(--lobe-color-fill-tertiary) 100%)',
                borderRadius: 12,
                padding: '16px',
                width: '100%',
              }}>
              <Avatar
                avatar={avatarUrl}
                size={56}
                style={{ border: '3px solid var(--lobe-color-bg-container)', borderRadius: 14 }}
              />
              <Flexbox flex={1} gap={4} style={{ minWidth: 0 }}>
                <div style={{ fontSize: 17, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>拾一 Innei</div>
                <div style={{
                    color: 'var(--lobe-color-text-3)',
                    fontSize: 12,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                  github.com/Innei
                </div>
              </Flexbox>
              <Tag color="purple" style={{ fontWeight: 600 }}>
                <Sparkles size={12} style={{ marginRight: 4 }} />
                Pro
              </Tag>
            </Flexbox>

            {/* Stats Row with icons */}
            <Flexbox gap={10} horizontal>
              <StatItem
                color="var(--lobe-color-primary)"
                icon={MessageSquare}
                label="Neko"
                value={4}
              />
              <StatItem
                color="var(--lobe-color-success)"
                icon={BarChart2}
                label="收藏"
                value={13}
              />
              <StatItem
                color="var(--lobe-color-warning)"
                icon={Sparkles}
                label="对话"
                value={114}
              />
            </Flexbox>

            {/* Divider */}
            <div
              style={{
                background: 'var(--lobe-color-border)',
                height: 1,
                margin: '4px 0',
              }}
            />

            {/* Menu Items */}
            <Flexbox gap={2}>
              <MenuItem icon={Settings}>应用设置</MenuItem>
              <MenuItem icon={CreditCard}>API管理</MenuItem>
              <MenuItem icon={Download}>导入数据</MenuItem>
            </Flexbox>

            {/* Divider */}
            <div
              style={{
                background: 'var(--lobe-color-border)',
                height: 1,
                margin: '4px 0',
              }}
            />

            {/* Logout with danger style */}
            <Button
              block
              icon={<LogOut size={16} />}
              style={{
                color: 'var(--lobe-color-error)',
                justifyContent: 'flex-start',
                padding: '10px 16px',
              }}
              type="text"
            >
              退出登录
            </Button>
          </Flexbox>
        }
        placement="bottomRight"
        trigger="click"
      >
        <button
          style={{
            background: 'var(--lobe-color-fill-secondary)',
            border: '1px solid var(--lobe-color-border)',
            borderRadius: 14,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '10px 16px',
            transition: 'all 0.2s',
            whiteSpace: 'nowrap',
            outline: 'none',
          }}
        >
          <Avatar
            avatar={avatarUrl}
            size={42}
            style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
          />
          <Flexbox align="center" gap={6} horizontal style={{ minWidth: 0 }}>
            <span style={{ fontSize: 15, fontWeight: 600, whiteSpace: 'nowrap' }}>拾一</span>
            <ChevronDown
              size={16}
              style={{ color: 'var(--lobe-color-text-3)', transition: 'transform 0.2s' }}
            />
          </Flexbox>
        </button>
      </Popover>
    </Flexbox>
  );
};

User.displayName = 'User';

export default User;