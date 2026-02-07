import { Modal, Button, Input, Flexbox, Icon, Tooltip, toast, Avatar } from '@lobehub/ui';
import { 
  User, Fingerprint, Link as LinkIcon, FileText, 
  ChevronDown, ChevronRight, CircleHelp,
  RefreshCw, Sparkles, XCircle, CheckCircle2, AlertCircle
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { authService } from '@/services/auth';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLoginSuccess: () => void;
}

const LoginModal = ({ isOpen, onClose, onLoginSuccess }: LoginModalProps) => {
  const [username, setUsername] = useState('');
  const [bangumiId, setBangumiId] = useState('');
  const [bangumiName, setBangumiName] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [sign, setSign] = useState('');
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const [isChecking, setIsChecking] = useState(false);
  const [userExists, setUserExists] = useState<boolean | null>(null);
  const [existingUserInfo, setExistingUserInfo] = useState<{ 
    avatar_url?: string; username?: string; bangumi_id?: string; bangumi_name?: string; sign?: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!username.trim()) {
      setUserExists(null);
      setExistingUserInfo(null);
      setError(null);
      setBangumiId('');
      setAvatarUrl('');
      setSign('');
      return;
    }

    setIsChecking(true);
    const timer = setTimeout(async () => {
      try {
        const user = await authService.checkUser(username);
        
        if (user) {
          setUserExists(true);
          setExistingUserInfo({
            avatar_url: user.avatar_url || undefined,
            username: user.username,
            bangumi_id: user.bangumi_id ? String(user.bangumi_id) : undefined,
            bangumi_name: user.bangumi_name || undefined,
            sign: user.sign || undefined
          });
          setBangumiId(user.bangumi_id ? String(user.bangumi_id) : '');
          setBangumiName(user.bangumi_name || '');
          setAvatarUrl(user.avatar_url || '');
          setSign(user.sign || '');
        } else {
          setUserExists(false);
          setExistingUserInfo(null);
          setBangumiId('');
          setAvatarUrl('');
          setSign('');
        }
      } catch (e) {
        console.error("检测失败", e);
        setError('检测失败，请稍后重试');
      } finally {
        setIsChecking(false);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [username]);

  const handleLogin = async () => {
    try {
      if (!username.trim()) {
        toast.error({
          title: '登录失败',
          description: '请输入用户名',
          icon: XCircle,
          duration: 3000,
        });
        return;
      }

      setLoading(true);

      const loginData = {
        username,
        bangumi_id: bangumiId ? parseInt(bangumiId) : undefined,
        bangumi_name: bangumiName || undefined,
        avatar_url: avatarUrl || undefined,
        sign: sign || undefined,
      };

      const data = await authService.login(loginData);

      localStorage.setItem('token', data.access_token);

      setLoading(false);
      onClose();
      onLoginSuccess();
    } catch (err) {
      console.error('登录错误:', err);
      toast.error({
        title: '登录失败',
        description: err instanceof Error ? err.message : '登录失败，请重试',
        icon: XCircle,
        duration: 3000,
      });
      setLoading(false);
    }
  };

  const handleSyncBangumi = async () => {
    if (!bangumiName) {
      toast.error({
        title: '同步失败',
        description: '请先输入 Bangumi 用户名',
        icon: XCircle,
        duration: 3000,
      });
      return;
    }

    try {
      setSyncing(true);

      const userInfo = await authService.syncBangumi(bangumiName);

      if (userInfo.avatar?.large) {
        setAvatarUrl(userInfo.avatar.large);
      }
      if (userInfo.sign) {
        setSign(userInfo.sign);
      }
      
      // 使用同步结果中的 ID 和用户名更新状态
      if (userInfo.id) {
        setBangumiId(String(userInfo.id));
      }
      if (userInfo.username) {
        setBangumiName(userInfo.username);
      }

      toast.success({
        title: '同步成功',
        description: '已从 Bangumi 同步用户信息',
        duration: 3000,
      });

    } catch (err) {
      console.error('同步 Bangumi 信息错误:', err);
      toast.error({
        title: '同步失败',
        description: err instanceof Error ? err.message : '同步失败，请检查 Bangumi 用户名是否正确',
        icon: XCircle,
        duration: 3000,
      });
    } finally {
      setSyncing(false);
    }
  };

  const FieldLabel = ({ 
    icon, 
    title, 
    required, 
    tooltip 
  }: { 
    icon: any, 
    title: string, 
    required?: boolean, 
    tooltip?: string 
  }) => {
    const LabelContent = (
      <Flexbox horizontal align="center" gap={4} style={{ marginBottom: 6, fontSize: 13, color: 'var(--lobe-color-text-2)' }}>
        <Icon icon={icon} size={ 14 } />
        <span style={tooltip ? { 
          borderBottom: '1px dashed var(--lobe-color-text-3)',
          cursor: 'help'
        } : {}}>
          {title}
        </span>
        {required && <span style={{ color: 'var(--lobe-color-error)' }}>*</span>}
      </Flexbox>
    );

    return tooltip ? (
      <Tooltip title={tooltip} placement="topLeft">
        <div style={{ width: 'fit-content' }}>
          {LabelContent}
        </div>
      </Tooltip>
    ) : (
      LabelContent
    );
  };

  return (
    <>
      <Modal
        title={userExists === true ? "欢迎回来" : "登录 / 注册"}
        open={isOpen}
        onCancel={onClose}
        onOk={handleLogin}
        okText={loading ? "处理中..." : (userExists === true ? "登录" : "注册并登录")}
        cancelText="取消"
        centered
        width={400}
        okButtonProps={{ loading }}
      >
        {error && (
          <Flexbox 
            horizontal 
            align="center" 
            gap={8}
            style={{ 
              marginBottom: 16, 
              padding: '8px 12px', 
              background: 'var(--lobe-color-error-bg)', 
              borderRadius: 6,
              fontSize: 12,
              color: 'var(--lobe-color-error)'
            }}
          >
            <Icon icon={AlertCircle} size={14} />
            <span>{error}</span>
          </Flexbox>
        )}

        <Flexbox gap={16} style={{ marginBottom: 16 }}>
          <div>
            <FieldLabel icon={User} title="用户名" required tooltip="登录用的唯一标识" />
            <div style={{ position: 'relative' }}>
              <Input 
                placeholder="请输入用户名" 
                value={username} 
                onChange={e => setUsername(e.target.value)} 
                size="large" 
                variant="filled"
                status={userExists === true ? 'success' : undefined}
              />
              {isChecking && (
                <div style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--lobe-color-text-3)' }}>
                  <Icon icon={RefreshCw} className="animate-spin" />
                </div>
              )}
            </div>

            {userExists === true && existingUserInfo && (
              <Flexbox 
                horizontal 
                align="center" 
                gap={12} 
                style={{ 
                  marginTop: 12, 
                  padding: 12, 
                  background: 'var(--lobe-color-fill-2)', 
                  borderRadius: 8,
                  animation: 'fade-in 0.3s ease'
                }}
              >
                <Avatar src={existingUserInfo.avatar_url} size={40} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>{existingUserInfo.username}</div>
                  <div style={{ fontSize: 12, color: 'var(--lobe-color-text-3)' }}>检测到已有账号，点击登录即可</div>
                </div>
                <Icon icon={CheckCircle2} style={{ marginLeft: 'auto', color: 'var(--lobe-color-success)' }} />
              </Flexbox>
            )}
          </div>

          {userExists === false && (
            <div style={{ 
              marginBottom: 16, 
              padding: '8px 12px', 
              background: 'var(--lobe-color-primary-bg)', 
              borderRadius: 6,
              fontSize: 12,
              color: 'var(--lobe-color-primary)'
            }}>
              👋 看起来您是新朋友，请完善以下信息完成注册。
            </div>
          )}

          <div>
            <FieldLabel icon={Fingerprint} title="Bangumi 用户名" tooltip="输入用户名后点击右侧按钮可同步资料" />
            <Flexbox horizontal gap={8}>
              <Input
                type="text"
                placeholder="请输入用户名 (可选)"
                value={bangumiName}
                onChange={(e) => setBangumiName(e.target.value)}
                disabled={loading || syncing}
                style={{ flex: 1 }}
              />
              <Tooltip title="从 Bangumi 同步头像和昵称">
                <Button 
                  onClick={handleSyncBangumi}
                  loading={syncing}
                  icon={<Icon icon={syncing ? RefreshCw : Sparkles} />}
                  style={{ flex: 'none' }}
                >
                  同步
                </Button>
              </Tooltip>
            </Flexbox>
            {/* 隐藏的输入字段，用于存储 bangumi_id */}
            <input 
              type="hidden" 
              value={bangumiId} 
              onChange={(e) => setBangumiId(e.target.value)} 
            />
          </div>

          <Flexbox 
            onClick={() => setShowDetails(!showDetails)}
            horizontal 
            align="center" 
            style={{ cursor: 'pointer', userSelect: 'none', fontSize: 12, color: 'var(--lobe-color-text-3)', margin: '12px 0' }}
          >
            <Icon icon={showDetails ? ChevronDown : ChevronRight} />
            <span style={{ marginLeft: 4 }}>更多信息（头像、签名）</span>
          </Flexbox>

          {showDetails && (
            <Flexbox direction="vertical" gap={12}>
              <div>
                <FieldLabel icon={Fingerprint} title="Bangumi ID" tooltip="Bangumi的用户ID" />
                <Input placeholder="Bangumi ID" value={bangumiId} onChange={e => setBangumiId(e.target.value)} />
              </div>
              <div>
                <FieldLabel icon={LinkIcon} title="头像 URL" tooltip="支持图片直链" />
                <Flexbox horizontal gap={12} align="center">
                  <Input style={{flex:1}} placeholder="https://..." value={avatarUrl} onChange={e => setAvatarUrl(e.target.value)} />
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%', 
                    background: '#f5f5f5', overflow: 'hidden', flex: 'none',
                    border: '1px solid var(--lobe-color-border)'
                  }}>
                    {avatarUrl && <img src={avatarUrl} alt="preview" style={{width:'100%', height:'100%', objectFit:'cover'}} />}
                  </div>
                </Flexbox>
              </div>

              <div>
                <FieldLabel icon={FileText} title="个性签名" />
                <Input placeholder="签名..." value={sign} onChange={e => setSign(e.target.value)} />
              </div>
            </Flexbox>
          )}
        </Flexbox>
      </Modal>
    </>
  );
};

export default LoginModal;
