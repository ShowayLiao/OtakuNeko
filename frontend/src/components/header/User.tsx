import { Avatar, Button, Flexbox, Popover, Tag, toast } from '@lobehub/ui';
import { createStaticStyles } from 'antd-style';
import {
  BarChart2,
  ChevronDown,
  CreditCard,
  Download,
  LogOut,
  LogIn,
  MessageSquare,
  Settings,
  Sparkles,
  Film,
  Book,
  Music,
  Gamepad2,
  Users,
  RefreshCw,

} from 'lucide-react';
import type { FC } from 'react';
import { useEffect, useState } from 'react';
import LoginModal from '../Modal/LoginModal';
import ImportModal from '../Modal/ImportModal';
import ApiKeyModal from '../Modal/ApiKeyModal';
import { dashboardService, type DashboardStats } from '@/services/dashboard';
import { collectionService } from '@/services/collections';

// 定义用户信息类型
interface UserInfo {
  id: number;
  username: string;
  avatar_url: string | null;
  bangumi_id: number | null;
  sign: string | null;
  created_at: string;
}

const MenuItem = ({ icon: Icon, children, onClick, loading = false }: { children: string; icon: React.ElementType; onClick?: () => void; loading?: boolean }) => (
  <Button
    block
    icon={loading ? undefined : <Icon size={16} />}
    loading={loading}
    style={{
      justifyContent: 'flex-start',
      padding: '10px 16px',
      transition: 'all 0.2s',
    }}
    type="text"
    onClick={onClick}
    disabled={loading}
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
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [statsLoading, setStatsLoading] = useState<boolean>(false);
  const [syncLoading, setSyncLoading] = useState<boolean>(false);
  const [popoverOpen, setPopoverOpen] = useState(false);

  // 从后端API获取用户信息
  const fetchUserInfo = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // 从localStorage获取token
      const token = localStorage.getItem('token');
      if (!token) {
        throw new Error('No authentication token found');
      }

      // 调用后端API获取用户信息
      const response = await fetch('http://localhost:8000/api/v1/users/me', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch user info: ${response.statusText}`);
      }

      const data = await response.json();
      setUserInfo(data);
      
      // 用户信息获取成功后，获取统计数据
      fetchStats();
    } catch (err) {
      console.error('Error fetching user info:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch user info');
    } finally {
      setLoading(false);
    }
  };

  // 获取统计数据
  const fetchStats = async () => {
    try {
      setStatsLoading(true);
      const data = await dashboardService.getStats();
      setStats(data);
    } catch (err) {
      console.error('Error fetching stats:', err);
    } finally {
      setStatsLoading(false);
    }
  };

  // 组件挂载时获取用户信息
  useEffect(() => {
    fetchUserInfo();
  }, []);

  // 登录成功后的处理函数
  const handleLoginSuccess = () => {
    // 登录成功后重新获取用户信息
    fetchUserInfo();
  };

  // 退出登录函数
  const handleLogout = () => {
    // 清除localStorage中的token
    localStorage.removeItem('token');
    // 重置用户信息状态
    setUserInfo(null);
    setError('No authentication token found');
  };

  // 同步收藏函数
  const handleSyncCollections = async () => {
    setSyncLoading(true);
    
    try {
      // 使用 toast.promise 实现持久化的 Toast 提示
      const response = await toast.promise(
        collectionService.syncBgm(),
        {
          loading: '正在同步收藏数据...',
          success: (response) => `同步成功！共同步了 ${response.sync_count} 条收藏记录`,
          error: (error) => `同步失败：${error instanceof Error ? error.message : '未知错误'}`
        }
      );
      
      // 重新获取统计数据，更新UI
      fetchStats();
    } catch (error) {
      console.error('Error syncing collections:', error);
    } finally {
      setSyncLoading(false);
    }
  };

  // 使用从API获取的头像URL或默认值
  const avatarUrl = userInfo?.avatar_url || 'https://cdn.jsdelivr.net/gh/Innei/static@master/avatar.png';
  
  // 检查是否为尚未登录的状态（没有token或token无效）
  const isNotLoggedIn = error === 'No authentication token found' || error?.includes('Unauthorized');
  
  // 使用从API获取的用户名或根据状态显示不同内容
  const username = userInfo?.username || (isNotLoggedIn ? '尚未登录' : '拾一');
  
  // 使用从API获取的签名或根据状态显示不同内容
  const userSign = userInfo?.sign || (isNotLoggedIn ? '尚未同步' : '本地用户');

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
                <div style={{ fontSize: 17, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {loading ? '加载中...' : isNotLoggedIn ? username : error ? '错误' : username}
                </div>
                <div style={{
                    color: 'var(--lobe-color-text-3)',
                    fontSize: 12,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                  {loading ? '加载中...' : isNotLoggedIn ? userSign : error ? '无法加载用户信息' : userSign}
                </div>
              </Flexbox>
              <Tag color={isNotLoggedIn ? "gray" : "green"} style={{ fontWeight: 600 }}>
                {isNotLoggedIn ? (
                  <>
                    未同步
                  </>
                ) : (
                  <>
                    已登录
                  </>
                )}
              </Tag>
            </Flexbox>

            {/* Stats Row with icons */}
            <Flexbox gap={10} horizontal>
              <StatItem
                color="var(--lobe-color-success)"
                icon={Film}
                label="动画"
                value={stats?.anime || 0}
              />
              <StatItem
                color="var(--lobe-color-warning)"
                icon={Book}
                label="书籍"
                value={stats?.books || 0}
              />
              <StatItem
                color="var(--lobe-color-error)"
                icon={Gamepad2}
                label="游戏"
                value={stats?.games || 0}
              />
              <StatItem
                color="var(--lobe-color-info)"
                icon={Users}
                label="三次元"
                value={stats?.real || 0}
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
              <MenuItem icon={CreditCard} onClick={() => {
                setIsApiKeyModalOpen(true);
                setPopoverOpen(false);
              }}>API管理</MenuItem>
              <MenuItem icon={RefreshCw} onClick={handleSyncCollections} loading={syncLoading}>同步收藏</MenuItem>
              <MenuItem icon={Download} onClick={() => {
                setIsImportModalOpen(true);
                setPopoverOpen(false);
              }}>导入数据</MenuItem>
            </Flexbox>

            {/* Divider */}
            <div
              style={{
                background: 'var(--lobe-color-border)',
                height: 1,
                margin: '4px 0',
              }}
            />

            {/* Login/Logout Button */}
            {isNotLoggedIn ? (
              <Button
                block
                icon={<LogIn size={16} />}
                style={{
                  color: 'var(--lobe-color-primary)',
                  justifyContent: 'flex-start',
                  padding: '10px 16px',
                }}
                type="text"
                onClick={() => {
                  setIsLoginModalOpen(true);
                  setPopoverOpen(false);
                }}
              >
                登录
              </Button>
            ) : (
              <Button
                block
                icon={<LogOut size={16} />}
                style={{
                  color: 'var(--lobe-color-error)',
                  justifyContent: 'flex-start',
                  padding: '10px 16px',
                }}
                type="text"
                onClick={handleLogout}
              >
                退出登录
              </Button>
            )}
          </Flexbox>
        }
        placement="bottomRight"
        trigger="click"
        open={popoverOpen}
        onOpenChange={setPopoverOpen}
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
          onClick={() => setPopoverOpen(!popoverOpen)}
        >
          <Avatar
            avatar={avatarUrl}
            size={42}
            style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
          />
          <Flexbox align="center" gap={6} horizontal style={{ minWidth: 0 }}>
            <span style={{ fontSize: 15, fontWeight: 600, whiteSpace: 'nowrap' }}>
              {loading ? '加载中...' : isNotLoggedIn ? username : error ? '错误' : username}
            </span>
            <ChevronDown
              size={16}
              style={{ color: 'var(--lobe-color-text-3)', transition: 'transform 0.2s' }}
            />
          </Flexbox>
        </button>
      </Popover>
      
      {/* Login Modal */}
      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={() => setIsLoginModalOpen(false)}
        onLoginSuccess={handleLoginSuccess}
      />
      
      {/* Import Modal */}
      <ImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
      />
      
      {/* API Key Modal */}
      <ApiKeyModal
        open={isApiKeyModalOpen}
        onClose={() => setIsApiKeyModalOpen(false)}
      />
    </Flexbox>
  );
};

User.displayName = 'User';

export default User;