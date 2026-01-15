// 本地认证工具函数，用于处理.env.local文件的读写操作

// 用户信息接口定义
export interface LocalUserInfo {
  username: string;
  aiHost: string;
  aiToken: string;
  bangumiId?: string;
  noBangumiAccount?: boolean;
}

// 环境配置接口定义
export interface EnvConfig {
  NEXT_PUBLIC_CLOUD_MODE: boolean;
  userInfo?: LocalUserInfo;
}

/**
 * 从环境变量中读取配置信息（客户端安全版本）
 * @returns EnvConfig对象，包含云端模式配置和用户信息
 */
export const readEnvConfig = (): EnvConfig => {
  try {
    // 从环境变量中读取云端模式配置
    const cloudMode = process.env.NEXT_PUBLIC_CLOUD_MODE?.toLowerCase() === 'true';
    
    // 注意：在客户端环境中，我们无法直接读取.env.local文件
    // 我们只能访问以NEXT_PUBLIC_开头的环境变量
    // 因此，用户信息需要通过其他方式存储（如localStorage）
    
    return {
      NEXT_PUBLIC_CLOUD_MODE: cloudMode,
      userInfo: undefined // 在客户端，我们不直接从.env文件读取用户信息
    };
  } catch (error) {
    console.error('Error reading env config:', error);
    return { NEXT_PUBLIC_CLOUD_MODE: true };
  }
};

/**
 * 从localStorage中读取用户信息
 * @returns LocalUserInfo | undefined 用户信息或undefined
 */
export const readUserInfoFromLocalStorage = (): LocalUserInfo | undefined => {
  try {
    const userInfoString = localStorage.getItem('localUserInfo');
    if (userInfoString) {
      const userInfo = JSON.parse(userInfoString);
      return validateUserInfo(userInfo) ? userInfo : undefined;
    }
    return undefined;
  } catch (error) {
    console.error('Error reading user info from localStorage:', error);
    return undefined;
  }
};

/**
 * 将用户信息写入localStorage
 * @param userInfo 用户信息
 * @returns boolean 是否成功写入
 */
export const writeUserInfoToLocalStorage = (userInfo: LocalUserInfo): boolean => {
  try {
    localStorage.setItem('localUserInfo', JSON.stringify(userInfo));
    return true;
  } catch (error) {
    console.error('Error writing user info to localStorage:', error);
    return false;
  }
};

/**
 * 验证用户信息的完整性和有效性
 * @param userInfo 用户信息
 * @returns boolean 是否有效
 */
export const validateUserInfo = (userInfo: Partial<LocalUserInfo>): userInfo is LocalUserInfo => {
  if (!userInfo.username || !userInfo.aiHost || !userInfo.aiToken) {
    return false;
  }
  
  // 用户名验证：3-20个字符，只能包含字母、数字、下划线和连字符
  const usernameRegex = /^[a-zA-Z0-9_-]{3,20}$/;
  if (!usernameRegex.test(userInfo.username.trim())) {
    return false;
  }
  
  // AI服务地址验证：完整URL格式
  const urlRegex = /^https?:\/\/[\w\-]+(\.[\w\-]+)+([\w\-\.,@?^=%&:/~\+#]*[\w\-\@?^=%&/~\+#])?$/;
  if (!urlRegex.test(userInfo.aiHost.trim())) {
    return false;
  }
  
  // AI Token验证：非空且长度≥16字符
  if (userInfo.aiToken.trim().length < 16) {
    return false;
  }
  
  return true;
};