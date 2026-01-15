"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { User, Server, Search, Loader2 } from 'lucide-react';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Checkbox } from '../ui/Checkbox';
import { useSettings } from '@/contexts/SettingsContext';
import { useToast } from '../ui/Toast';
import { fetchBangumiUser, BangumiUser, login, saveAiToken } from '@/lib/api';
import { readEnvConfig, readUserInfoFromLocalStorage, writeUserInfoToLocalStorage, LocalUserInfo } from '@/lib/localAuth';


interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  forceOpen?: boolean;
}

export function SettingsModal({ isOpen, onClose, forceOpen = false }: SettingsModalProps) {
  const { settings, updateSettings, userInfo: contextUserInfo, setUserInfo } = useSettings();
  const { toast } = useToast();
  
  const [formData, setFormData] = useState({
    username: settings.username,
    bangumiId: '',
    aiHost: settings.aiHost,
    aiToken: settings.aiToken
  });
  const [noBangumiAccount, setNoBangumiAccount] = useState(!contextUserInfo?.bangumi_id);
  const [isValidating, setIsValidating] = useState(false);
  const [showAiToken, setShowAiToken] = useState(false);
  
  const [validationErrors, setValidationErrors] = useState({
    username: '',
    aiHost: '',
    aiToken: '',
    bangumiId: ''
  });
  
  const isUpdatingRef = useRef(false);

  const resetModalState = useCallback(() => {
    setFormData({
      username: settings.username,
      bangumiId: contextUserInfo?.bangumi_id || '',
      aiHost: settings.aiHost,
      aiToken: settings.aiToken
    });
    setNoBangumiAccount(!contextUserInfo?.bangumi_id);
    setIsValidating(false);
    setValidationErrors({ username: '', aiHost: '', aiToken: '', bangumiId: '' });
    isUpdatingRef.current = false;
  }, [settings, contextUserInfo]);



  // 简化的用户信息检查逻辑，使用新的API结构
  // 注意：这里暂时移除了checkLocalUser的调用，因为后端文档中没有对应的接口
  // 后续可以根据实际需要添加或调整
  useEffect(() => {
    const timer = setTimeout(() => {
      const username = formData.username.trim();
      if (username && username.length > 0) {
        // 可以在这里添加用户名验证逻辑，但暂时不调用API
        // 因为后端文档中没有对应的checkLocalUser接口
      }
    }, 500);
    
    return () => clearTimeout(timer);
  }, [formData.username]);

  const handleSearchUser = useCallback(async () => {
    if (isUpdatingRef.current || isValidating) return;
    
    const bangumiId = formData.bangumiId.trim();
    if (!bangumiId) {
      toast({
        type: 'error',
        message: '请输入 Bangumi ID 或用户名'
      });
      return;
    }

    isUpdatingRef.current = true;
    setIsValidating(true);
    
    try {
      const userData = await fetchBangumiUser(bangumiId);
      if (userData) {
        toast({
          type: 'success',
          message: '用户信息获取成功'
        });
      } else {
        toast({
          type: 'error',
          message: '用户不存在，请检查 Bangumi ID 或用户名是否正确'
        });
      }
    } catch (error) {
      toast({
        type: 'error',
        message: error instanceof Error ? error.message : '无法获取用户信息'
      });
    } finally {
      setIsValidating(false);
      isUpdatingRef.current = false;
    }
  }, [formData.bangumiId, isValidating, toast]);

  // 生成用户名首字母头像
  const generateAvatar = useCallback((username: string) => {
    if (!username) return { initial: '?', backgroundColor: '#6b7280' };
    
    const initial = username.charAt(0).toUpperCase();
    // 基于用户名生成随机背景色，确保对比度
    const hash = username.split('').reduce((acc, char) => {
      return char.charCodeAt(0) + ((acc << 5) - acc);
    }, 0);
    
    const hue = Math.abs(hash) % 360;
    const backgroundColor = `hsl(${hue}, 70%, 60%)`;
    
    return { initial, backgroundColor };
  }, []);

  // 表单验证函数
  const validateForm = useCallback(() => {
    const errors = {
      username: '',
      aiHost: '',
      aiToken: '',
      bangumiId: ''
    };
    
    // 用户名验证：3-20个字符，只能包含字母、数字、下划线和连字符
    const usernameRegex = /^[a-zA-Z0-9_-]{3,20}$/;
    if (!formData.username.trim()) {
      errors.username = '用户名不能为空';
    } else if (!usernameRegex.test(formData.username.trim())) {
      errors.username = '用户名长度应为3-20个字符，只能包含字母、数字、下划线和连字符';
    }
    
    // AI服务地址验证：完整URL格式
    const urlRegex = /^https?:\/\/[\w\-]+(\.[\w\-]+)+([\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?$/;
    if (!formData.aiHost.trim()) {
      errors.aiHost = 'AI服务地址不能为空';
    } else if (!urlRegex.test(formData.aiHost.trim())) {
      errors.aiHost = '请输入有效的URL地址，包括协议(http/https)';
    }
    
    // AI Token验证：非空且长度≥16字符
    if (!formData.aiToken.trim()) {
      errors.aiToken = 'AI Token不能为空';
    } else if (formData.aiToken.trim().length < 16) {
      errors.aiToken = 'AI Token长度不能少于16个字符';
    }
    
    // Bangumi ID验证：如果不是无Bangumi账号，则需要验证
    if (!noBangumiAccount && !formData.bangumiId.trim()) {
      errors.bangumiId = 'Bangumi ID不能为空';
    }
    
    setValidationErrors(errors);
    
    // 检查是否有错误
    return !Object.values(errors).some(error => error !== '');
  }, [formData, noBangumiAccount]);
  
  // 实时验证单个字段
  const validateField = useCallback((field: keyof typeof formData, value: string) => {
    const errors = { ...validationErrors };
    
    switch (field) {
      case 'username':
        const usernameRegex = /^[a-zA-Z0-9_-]{3,20}$/;
        if (!value.trim()) {
          errors.username = '用户名不能为空';
        } else if (!usernameRegex.test(value.trim())) {
          errors.username = '用户名长度应为3-20个字符，只能包含字母、数字、下划线和连字符';
        } else {
          errors.username = '';
        }
        break;
        
      case 'aiHost':
        const urlRegex = /^https?:\/\/[\w\-]+(\.[\w\-]+)+([\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?$/;
        if (!value.trim()) {
          errors.aiHost = 'AI服务地址不能为空';
        } else if (!urlRegex.test(value.trim())) {
          errors.aiHost = '请输入有效的URL地址，包括协议(http/https)';
        } else {
          errors.aiHost = '';
        }
        break;
        
      case 'aiToken':
        if (!value.trim()) {
          errors.aiToken = 'AI Token不能为空';
        } else if (value.trim().length < 16) {
          errors.aiToken = 'AI Token长度不能少于16个字符';
        } else {
          errors.aiToken = '';
        }
        break;
        
      case 'bangumiId':
        if (!noBangumiAccount && !value.trim()) {
          errors.bangumiId = 'Bangumi ID不能为空';
        } else {
          errors.bangumiId = '';
        }
        break;
    }
    
    setValidationErrors(errors);
  }, [validationErrors, noBangumiAccount]);
  
  const handleSave = useCallback(async () => {
    if (!validateForm()) {
      toast({
        type: 'error',
        message: '请检查表单中的错误'
      });
      return;
    }

    try {
      // 1. 登录/注册用户，获取JWT token和用户信息
      const loginResponse = await login(formData.username.trim());
      
      // 2. 转换为BangumiUser类型用于上下文
      const bangumiUserInfo: BangumiUser = {
        id: loginResponse.user.id,
        username: loginResponse.user.username,
        nickname: loginResponse.user.nickname,
        sign: loginResponse.user.sign,
        avatar: {
          large: loginResponse.user.avatar_url || '',
          medium: loginResponse.user.avatar_url || '',
          small: loginResponse.user.avatar_url || ''
        },
        bangumi_id: loginResponse.user.bangumi_id || undefined
      };
      setUserInfo(bangumiUserInfo);
      
      // 3. 保存AI Token（根据环境模式自动应用存储策略）
      saveAiToken(formData.aiToken.trim());
      
      // 4. 更新设置
      updateSettings({
        username: formData.username.trim(),
        bangumiToken: noBangumiAccount ? undefined : formData.bangumiId.trim(),
        aiHost: formData.aiHost.trim(),
        aiToken: formData.aiToken.trim()
      }, false);
      
      // 5. 检查是否为本地模式，如果是则将用户信息写入localStorage
      const cloudMode = process.env.NEXT_PUBLIC_CLOUD_MODE?.toLowerCase() === 'true';
      if (!cloudMode) {
        const userInfoToSave: LocalUserInfo = {
          username: formData.username.trim(),
          aiHost: formData.aiHost.trim(),
          aiToken: formData.aiToken.trim(),
          bangumiId: noBangumiAccount ? undefined : formData.bangumiId.trim(),
          noBangumiAccount: noBangumiAccount
        };
        
        // 写入用户信息到localStorage
        const writeSuccess = writeUserInfoToLocalStorage(userInfoToSave);
        if (!writeSuccess) {
          console.error('写入用户信息到localStorage失败');
          toast({
            type: 'warning',
            message: '设置已保存，但用户信息写入本地存储失败，下次启动需要重新登录',
            duration: 5000
          });
        }
      }
      
      toast({
        type: 'success',
        message: forceOpen ? '开始使用' : '进入系统',
        duration: 3000
      });

      onClose();
    } catch (error) {
      console.error('Error saving settings:', error);
      
      let errorMessage = '保存设置失败';
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as { response?: { data?: { detail?: string }, status?: number } };
        if (axiosError.response?.data?.detail) {
          errorMessage = axiosError.response.data.detail;
        } else if (axiosError.response?.status === 401) {
          errorMessage = '认证失败，请检查用户名';
        } else if (axiosError.response?.status === 400) {
          errorMessage = '请求参数错误';
        }
      }
      
      toast({
        type: 'error',
        message: errorMessage,
        duration: 5000
      });
    }
  }, [formData, validateForm, updateSettings, setUserInfo, toast, onClose, noBangumiAccount, forceOpen]);

  const handleCancel = useCallback(() => {
    try {
      resetModalState();
      onClose();
    } catch (error) {
      console.error('Error canceling settings:', error);
    }
  }, [resetModalState, onClose]);

  const handleUsernameChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newUsername = e.target.value;
    setFormData(prev => ({ ...prev, username: newUsername }));
    
    // 实时验证用户名
    validateField('username', newUsername);
  }, [validateField]);

  // 处理AI服务地址变化
  const handleAiHostChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newAiHost = e.target.value;
    setFormData(prev => ({ ...prev, aiHost: newAiHost }));
    // 实时验证AI服务地址
    validateField('aiHost', newAiHost);
  }, [validateField]);

  // 处理AI Token变化
  const handleAiTokenChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newAiToken = e.target.value;
    setFormData(prev => ({ ...prev, aiToken: newAiToken }));
    // 实时验证AI Token
    validateField('aiToken', newAiToken);
  }, [validateField]);

  // 处理Bangumi ID变化
  const handleBangumiIdChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newBangumiId = e.target.value;
    setFormData(prev => ({ ...prev, bangumiId: newBangumiId }));
    // 实时验证Bangumi ID
    validateField('bangumiId', newBangumiId);
  }, [validateField]);

  const handleNoBangumiAccountToggle = useCallback((checked: boolean | 'indeterminate') => {
    const isChecked = checked === true;
    setNoBangumiAccount(isChecked);
    
    if (isChecked) {
      setFormData(prev => ({ ...prev, bangumiId: '' }));
    }
  }, []);

  if (!isOpen) return null;

  // 生成用户名首字母头像
  const avatarInfo = generateAvatar(formData.username.trim() || 'User');
  
  return (
    <>
      <Dialog isOpen={isOpen} onClose={handleCancel} title={forceOpen ? "欢迎！请完成初始设置" : "全局设置"} forceOpen={forceOpen}>
        <div className="space-y-6 py-4">
          <div className="grid gap-6 md:grid-cols-[auto_1fr] items-start">
            <div className="w-full md:w-[120px] flex-shrink-0">
              <div className="space-y-3">
                <div className="text-sm font-medium text-gray-700 dark:text-gray-300 text-center">
                  头像
                </div>
                <div className="relative aspect-square">
                  <div className="w-full h-full rounded-lg flex items-center justify-center text-white text-4xl font-bold" style={{ backgroundColor: avatarInfo.backgroundColor }}>
                    {avatarInfo.initial}
                  </div>
                </div>
              </div>
            </div>
            <div className="space-y-6 flex-1">
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <User className="w-5 h-5 text-gray-500" />
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">用户配置</h3>
                </div>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      用户名 <span className="text-red-500">*</span>
                    </label>
                    <Input type="text" value={formData.username} onChange={handleUsernameChange} placeholder="请输入用户名" required className={validationErrors.username ? 'border-red-500' : ''} />
                    {validationErrors.username && (
                      <p className="text-xs text-red-500 dark:text-red-400">{validationErrors.username}</p>
                    )}
                    <p className="text-xs text-gray-500 dark:text-gray-400">本地数据库唯一标识</p>
                  </div>
                  <div className="space-y-2">
                    <Checkbox id="no-bangumi-account" checked={noBangumiAccount} onCheckedChange={handleNoBangumiAccountToggle} />
                    <label htmlFor="no-bangumi-account" className="text-sm font-normal text-gray-700 dark:text-gray-300 cursor-pointer ml-2">我没有 Bangumi 账号</label>
                  </div>
                  {!noBangumiAccount && (
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Bangumi ID <span className="text-red-500">*</span>
                      </label>
                      <div className="flex items-center gap-2">
                        <Input type="text" value={formData.bangumiId} onChange={handleBangumiIdChange} placeholder="输入 Bangumi ID 或用户名" disabled={isValidating} className={validationErrors.bangumiId ? 'border-red-500' : ''} />
                        <Button size="icon" variant="outline" onClick={handleSearchUser} disabled={isValidating} className="shrink-0 h-10 w-10 p-0 flex items-center justify-center" title="验证 Bangumi 账号">
                          {isValidating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                        </Button>
                      </div>
                      {validationErrors.bangumiId && (
                        <p className="text-xs text-red-500 dark:text-red-400">{validationErrors.bangumiId}</p>
                      )}
                      <p className="text-xs text-gray-500 dark:text-gray-400">同步 Bangumi 账号。如果是中文用户名，请输入数字 ID；如果是英文用户名，输入用户名即可。</p>
                    </div>
                  )}

                </div>
              </div>
              <div className="border-t border-gray-200 dark:border-gray-700" />
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Server className="w-5 h-5 text-gray-500" />
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">AI 服务配置</h3>
                </div>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      AI 服务地址 <span className="text-red-500">*</span>
                    </label>
                    <Input type="url" value={formData.aiHost} onChange={handleAiHostChange} placeholder="http://localhost:8000" required className={validationErrors.aiHost ? 'border-red-500' : ''} />
                    {validationErrors.aiHost && (
                      <p className="text-xs text-red-500 dark:text-red-400">{validationErrors.aiHost}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      AI Token <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <Input type={showAiToken ? "text" : "password"} value={formData.aiToken} onChange={handleAiTokenChange} placeholder="请输入 AI 服务 Token" required className={validationErrors.aiToken ? 'border-red-500 pr-10' : 'pr-10'} />
                      <button type="button" onClick={() => setShowAiToken(!showAiToken)} className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                        {showAiToken ? (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                          </svg>
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                        )}
                      </button>
                    </div>
                    {validationErrors.aiToken && (
                      <p className="text-xs text-red-500 dark:text-red-400">{validationErrors.aiToken}</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button variant="outline" onClick={handleCancel}>取消</Button>
            <Button onClick={handleSave}>{forceOpen ? '开始使用' : '进入系统'}</Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
