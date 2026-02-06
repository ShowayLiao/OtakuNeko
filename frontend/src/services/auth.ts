import { request } from './client';

// 登录请求参数
export interface LoginRequest {
  username: string;
  bangumi_id?: number;
  bangumi_name?: string;
  avatar_url?: string;
  sign?: string;
}

// 登录响应
export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    username: string;
    avatar_url: string | null;
    bangumi_id: number | null;
    bangumi_name: string | null;
    sign: string | null;
    created_at: string;
  };
}

// 用户信息
export interface UserInfo {
  id: number;
  username: string;
  avatar_url: string | null;
  bangumi_id: number | null;
  bangumi_name: string | null;
  sign: string | null;
  created_at: string;
}

// Bangumi 用户信息
export interface BangumiUserInfo {
  id: number;
  username: string;
  nickname: string;
  sign: string | null;
  avatar: {
    large: string;
    medium: string;
    small: string;
  };
  url: string;
  user_group: number;
}

// 认证服务
export const authService = {
  // 检查用户是否存在
  async checkUser(username: string): Promise<UserInfo | null> {
    try {
      const user = await request<UserInfo>(`/users/username/${username}`);
      return user;
    } catch (error) {
      // 404 错误表示用户不存在，检查错误消息中是否包含 '用户不存在'
      if ((error as Error).message.includes('用户不存在')) {
        return null;
      }
      throw error;
    }
  },

  // 用户登录
  async login(data: LoginRequest): Promise<LoginResponse> {
    return request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // 从 Bangumi 同步用户信息
  async syncBangumi(bangumiId: string): Promise<BangumiUserInfo> {
    return request<BangumiUserInfo>(`/bangumi/user/${bangumiId}`);
  },
};
