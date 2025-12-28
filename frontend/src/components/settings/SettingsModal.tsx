"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { Save, User, Server, Check, Search, Loader2, UserCircle, Upload, XCircle, Grid3x3 } from 'lucide-react';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Checkbox } from '../ui/Checkbox';
import { useSettings } from '@/contexts/SettingsContext';
import { useToast } from '../ui/Toast';
import { fetchBangumiUser, BangumiUser, registerLocalUser, checkLocalUser } from '@/lib/api';
import { GridImportModal } from './GridImportModal';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  forceOpen?: boolean;
}

export function SettingsModal({ isOpen, onClose, forceOpen = false }: SettingsModalProps) {
  const { settings, isRemembered, updateSettings, userInfo: contextUserInfo, setUserInfo } = useSettings();
  const { toast } = useToast();
  
  const [formData, setFormData] = useState({
    username: settings.username,
    bangumiId: '',
    aiHost: settings.aiHost,
    aiToken: settings.aiToken
  });
  const [noBangumiAccount, setNoBangumiAccount] = useState(!contextUserInfo?.bangumi_id);
  const [rememberMe, setRememberMe] = useState(isRemembered);
  const [previewUser, setPreviewUser] = useState<BangumiUser | null>(contextUserInfo);
  const [isValidating, setIsValidating] = useState(false);
  const [customAvatar, setCustomAvatar] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isGridImportOpen, setIsGridImportOpen] = useState(false);
  
  const isUpdatingRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetModalState = useCallback(() => {
    setFormData({
      username: settings.username,
      bangumiId: contextUserInfo?.bangumi_id || '',
      aiHost: settings.aiHost,
      aiToken: settings.aiToken
    });
    setNoBangumiAccount(!contextUserInfo?.bangumi_id);
    setRememberMe(isRemembered);
    setPreviewUser(contextUserInfo);
    setCustomAvatar(null);
    setIsValidating(false);
    setIsUploading(false);
    isUpdatingRef.current = false;
  }, [settings, isRemembered, contextUserInfo]);

  useEffect(() => {
    if (isOpen) {
      resetModalState();
    }
  }, [isOpen, resetModalState]);

  useEffect(() => {
    const timer = setTimeout(() => {
      const username = formData.username.trim();
      if (username && username.length > 0) {
        checkLocalUser(username).then(response => {
          if (response.found && response.user) {
            const foundUser: BangumiUser = {
              id: response.user.id,
              username: response.user.username,
              nickname: response.user.nickname,
              sign: response.user.sign,
              avatar: {
                large: response.user.avatar_url || '',
                medium: response.user.avatar_url || '',
                small: response.user.avatar_url || ''
              },
              bangumi_id: response.user.bangumi_id?.toString()
            };
            setPreviewUser(foundUser);
            
            if (response.user.bangumi_id) {
              setNoBangumiAccount(false);
              setFormData(prev => ({ ...prev, bangumiId: response.user!.bangumi_id!.toString() }));
            } else {
              setNoBangumiAccount(true);
            }
          }
        }).catch(error => {
          console.error('Error checking local user:', error);
        });
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
        setPreviewUser(userData);
        toast({
          type: 'success',
          message: '用户信息获取成功'
        });
      } else {
        setPreviewUser(null);
        toast({
          type: 'error',
          message: '用户不存在，请检查 Bangumi ID 或用户名是否正确'
        });
      }
    } catch (error) {
      setPreviewUser(null);
      toast({
        type: 'error',
        message: error instanceof Error ? error.message : '无法获取用户信息'
      });
    } finally {
      setIsValidating(false);
      isUpdatingRef.current = false;
    }
  }, [formData.bangumiId, isValidating, toast]);

  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      toast({
        type: 'error',
        message: '请选择图片文件'
      });
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      toast({
        type: 'error',
        message: '图片大小不能超过 2MB'
      });
      return;
    }

    setIsUploading(true);
    const reader = new FileReader();
    
    reader.onload = (event) => {
      try {
        const imageUrl = event.target?.result as string;
        setCustomAvatar(imageUrl);
        
        const username = formData.username.trim() || 'User';
        const localUser: BangumiUser = {
          id: contextUserInfo?.id || 0,
          username: username,
          nickname: username,
          sign: '本地用户',
          avatar: { large: imageUrl, medium: imageUrl, small: imageUrl }
        };
        setPreviewUser(localUser);
        
        toast({
          type: 'success',
          message: '头像上传成功'
        });
      } catch (error) {
        console.error('Error processing image:', error);
        toast({
          type: 'error',
          message: '图片处理失败'
        });
      } finally {
        setIsUploading(false);
      }
    };
    
    reader.onerror = () => {
      setIsUploading(false);
      toast({
        type: 'error',
        message: '图片上传失败'
      });
    };
    
    reader.readAsDataURL(file);
  }, [formData.username, toast, contextUserInfo]);

  const handleRemoveAvatar = useCallback(() => {
    setCustomAvatar(null);
    const username = formData.username.trim() || 'User';
    const localUser: BangumiUser = {
      id: contextUserInfo?.id || 0,
      username: username,
      nickname: username,
      sign: '本地用户',
      avatar: { large: '', medium: '', small: '' }
    };
    setPreviewUser(localUser);
  }, [formData.username, contextUserInfo]);

  const handleSave = useCallback(async () => {
    if (!formData.username.trim()) {
      toast({
        type: 'error',
        message: '用户名不能为空'
      });
      return;
    }

    if (!formData.aiHost.trim()) {
      toast({
        type: 'error',
        message: 'AI 服务地址不能为空'
      });
      return;
    }

    if (!formData.aiToken.trim()) {
      toast({
        type: 'error',
        message: 'AI Token 不能为空'
      });
      return;
    }

    try {
      if (noBangumiAccount) {
        const username = formData.username.trim();
        
        try {
          const registeredUser = await registerLocalUser({
            username: username,
            avatar: customAvatar || undefined
          });
          
          const localUserInfo: BangumiUser = {
            id: registeredUser.id,
            username: registeredUser.username,
            nickname: registeredUser.username,
            sign: '本地用户',
            avatar: {
              large: registeredUser.avatar_url || customAvatar || '',
              medium: registeredUser.avatar_url || customAvatar || '',
              small: registeredUser.avatar_url || customAvatar || ''
            }
          };
          
          setUserInfo(localUserInfo);
          updateSettings({
            username: username,
            bangumiToken: undefined,
            aiHost: formData.aiHost.trim(),
            aiToken: formData.aiToken.trim()
          }, rememberMe);
          
          toast({
            type: 'success',
            message: '本地用户注册成功'
          });
        } catch (error) {
          console.error('Error registering local user:', error);
          
          if (error && typeof error === 'object' && 'response' in error) {
            const axiosError = error as { response?: { data?: { detail?: string } } };
            if (axiosError.response?.data?.detail) {
              toast({
                type: 'error',
                message: axiosError.response.data.detail
              });
              return;
            }
          }
          
          toast({
            type: 'error',
            message: '本地用户注册失败'
          });
          return;
        }
      } else {
        if (!formData.bangumiId.trim()) {
          toast({
            type: 'error',
            message: '请输入 Bangumi ID'
          });
          return;
        }

        updateSettings({
          username: formData.username.trim(),
          bangumiToken: formData.bangumiId.trim(),
          aiHost: formData.aiHost.trim(),
          aiToken: formData.aiToken.trim()
        }, rememberMe);

        if (previewUser) {
          setUserInfo(previewUser);
        }
      }

      toast({
        type: 'success',
        message: '设置已保存'
      });

      onClose();
    } catch (error) {
      console.error('Error saving settings:', error);
      toast({
        type: 'error',
        message: '保存设置失败'
      });
    }
  }, [formData, previewUser, rememberMe, updateSettings, setUserInfo, toast, onClose, contextUserInfo, customAvatar, noBangumiAccount]);

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
    
    if (noBangumiAccount) {
      const username = newUsername.trim() || 'User';
      const localUser: BangumiUser = {
        id: contextUserInfo?.id || 0,
        username: username,
        nickname: username,
        sign: '本地用户',
        avatar: { large: customAvatar || '', medium: customAvatar || '', small: customAvatar || '' }
      };
      setPreviewUser(localUser);
    }
  }, [contextUserInfo, customAvatar, noBangumiAccount]);

  const handleFileButtonClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleNoBangumiAccountToggle = useCallback((checked: boolean | 'indeterminate') => {
    const isChecked = checked === true;
    setNoBangumiAccount(isChecked);
    
    if (isChecked) {
      setFormData(prev => ({ ...prev, bangumiId: '' }));
      setPreviewUser(null);
    }
  }, []);

  const handleRememberMeToggle = useCallback(() => {
    setRememberMe(prev => !prev);
  }, []);

  if (!isOpen) return null;

  return (
    <>
      <Dialog isOpen={isOpen} onClose={handleCancel} title={forceOpen ? "欢迎！请完成初始设置" : "全局设置"} forceOpen={forceOpen}>
        <div className="space-y-6 py-4">
          <div className="grid gap-6 md:grid-cols-[auto_1fr] items-start">
            <div className="w-full md:w-[180px] flex-shrink-0">
              <div className="space-y-3">
                <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  头像
                </div>
                <div 
                  onClick={handleFileButtonClick}
                  className="cursor-pointer group"
                >
                  {isUploading ? (
                    <div className="flex h-[180px] flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 dark:border-gray-600 dark:bg-gray-800/50">
                      <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
                    </div>
                  ) : previewUser?.avatar?.large || customAvatar ? (
                    <div className="relative group">
                      <img 
                        src={customAvatar || previewUser?.avatar?.large} 
                        alt={previewUser?.nickname || 'Avatar'}
                        className="w-full aspect-square rounded-lg object-cover border-2 border-gray-200 dark:border-gray-700 group-hover:border-primary transition-colors"
                      />
                      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center">
                        <Upload className="w-8 h-8 text-white" />
                      </div>
                    </div>
                  ) : (
                    <div className="h-[180px] flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 dark:border-gray-600 dark:bg-gray-800/50 group-hover:border-primary transition-colors">
                      <UserCircle className="w-16 h-16 text-gray-400 mb-2" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 text-center px-2">
                        点击上传头像
                      </p>
                    </div>
                  )}
                </div>
                <input
                  type="file"
                  ref={fileInputRef}
                  accept="image/*"
                  onChange={handleImageUpload}
                  className="hidden"
                  disabled={isUploading}
                />
                {customAvatar && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRemoveAvatar}
                    className="w-full flex items-center gap-2 text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                  >
                    <XCircle className="w-4 h-4" />
                    移除头像
                  </Button>
                )}
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
                    <Input
                      type="text"
                      value={formData.username}
                      onChange={handleUsernameChange}
                      placeholder="请输入用户名"
                      required
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      本地数据库唯一标识
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Checkbox 
                      id="no-bangumi-account" 
                      checked={noBangumiAccount}
                      onCheckedChange={handleNoBangumiAccountToggle}
                    />
                    <label 
                      htmlFor="no-bangumi-account" 
                      className="text-sm font-normal text-gray-700 dark:text-gray-300 cursor-pointer ml-2"
                    >
                      我没有 Bangumi 账号
                    </label>
                  </div>

                  {!noBangumiAccount && (
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Bangumi ID <span className="text-red-500">*</span>
                      </label>
                      <div className="flex items-center gap-2">
                        <Input
                          type="text"
                          value={formData.bangumiId}
                          onChange={(e) => setFormData({ ...formData, bangumiId: e.target.value })}
                          placeholder="输入 Bangumi ID 或用户名"
                          disabled={isValidating}
                        />
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={handleSearchUser}
                          disabled={isValidating}
                          className="shrink-0 h-10 w-10 p-0 flex items-center justify-center"
                          title="验证 Bangumi 账号"
                        >
                          {isValidating ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Search className="w-4 h-4" />
                          )}
                        </Button>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        同步 Bangumi 账号。如果是中文用户名，请输入数字 ID；如果是英文用户名，输入用户名即可。
                      </p>
                    </div>
                  )}

                  {noBangumiAccount && (
                    <div className="space-y-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setIsGridImportOpen(true)}
                        className="flex items-center gap-2 w-full"
                      >
                        <Grid3x3 className="w-4 h-4" />
                        九宫格导入基础信息
                      </Button>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        通过填写动画喜好宫格，快速生成你的二次元画像
                      </p>
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
                    <Input
                      type="url"
                      value={formData.aiHost}
                      onChange={(e) => setFormData({ ...formData, aiHost: e.target.value })}
                      placeholder="http://localhost:8000"
                      required
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      AI Token <span className="text-red-500">*</span>
                    </label>
                    <Input
                      type="password"
                      value={formData.aiToken}
                      onChange={(e) => setFormData({ ...formData, aiToken: e.target.value })}
                      placeholder="请输入 AI 服务 Token"
                      required
                    />
                  </div>
                </div>
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700" />

              <div className="space-y-2">
                <Checkbox 
                  id="remember-me" 
                  checked={rememberMe}
                  onCheckedChange={() => setRememberMe(!rememberMe)}
                />
                <label 
                  htmlFor="remember-me" 
                  className="text-sm font-normal text-gray-700 dark:text-gray-300 cursor-pointer ml-2"
                >
                  记住我的信息
                </label>
                <p className="text-xs text-gray-500 dark:text-gray-400 ml-6">
                  {rememberMe 
                    ? '你的信息将会被保存到本地数据库中（LocalStorage），我们不会另做他用，但也不保证其安全性，建议本地使用打开。'
                    : '你的用户信息将会保存在内存，静默 30min 后会自动删除。'
                  }
                </p>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button
              variant="outline"
              onClick={handleCancel}
            >
              取消
            </Button>
            <Button
              onClick={handleSave}
            >
              <Save className="w-4 h-4 mr-2" />
              保存设置
            </Button>
          </div>
        </div>
      </Dialog>

      <GridImportModal 
        isOpen={isGridImportOpen} 
        onClose={() => setIsGridImportOpen(false)} 
      />
    </>
  );
}
