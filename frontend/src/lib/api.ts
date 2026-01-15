import axios from 'axios';

// 创建axios实例
const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 30000, // 请求超时时间设置为30秒
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest', // 添加X-Requested-With头
  },
});

// 环境模式判断
const IS_CLOUD_MODE = process.env.NEXT_PUBLIC_CLOUD_MODE === 'true';

// JWT token管理
const CLOUD_TOKEN_KEY = 'auth_token'; // 云端模式下的token键名
const LOCAL_TOKEN_KEY = 'local_auth_token'; // 本地模式下的token键名
const LOCAL_AI_TOKEN_KEY = 'local_ai_token'; // 本地模式下的AI token键名

// 获取token
export const getToken = (): string | null => {
  const storage = IS_CLOUD_MODE ? sessionStorage : localStorage;
  const tokenKey = IS_CLOUD_MODE ? CLOUD_TOKEN_KEY : LOCAL_TOKEN_KEY;
  return storage.getItem(tokenKey);
};

// 保存token
export const saveToken = (token: string): void => {
  const storage = IS_CLOUD_MODE ? sessionStorage : localStorage;
  const tokenKey = IS_CLOUD_MODE ? CLOUD_TOKEN_KEY : LOCAL_TOKEN_KEY;
  storage.setItem(tokenKey, token);
};

// 删除token
export const removeToken = (): void => {
  const storage = IS_CLOUD_MODE ? sessionStorage : localStorage;
  const tokenKey = IS_CLOUD_MODE ? CLOUD_TOKEN_KEY : LOCAL_TOKEN_KEY;
  storage.removeItem(tokenKey);
};

// 保存AI Token
export const saveAiToken = (token: string): void => {
  if (!IS_CLOUD_MODE) {
    // 本地模式下才保存AI Token到localStorage
    localStorage.setItem(LOCAL_AI_TOKEN_KEY, token);
  }
};

// 获取AI Token
export const getAiToken = (): string | null => {
  if (IS_CLOUD_MODE) {
    // 云端模式下不从存储中获取AI Token
    return null;
  }
  return localStorage.getItem(LOCAL_AI_TOKEN_KEY);
};

// 删除AI Token
export const removeAiToken = (): void => {
  if (!IS_CLOUD_MODE) {
    localStorage.removeItem(LOCAL_AI_TOKEN_KEY);
  }
};

// 请求重试配置
const MAX_RETRIES = 2;
const RETRY_DELAY = 1000; // 1秒
const RETRYABLE_STATUS_CODES = [408, 502, 503, 504];

// 请求拦截器 - 添加Authorization头和日志
api.interceptors.request.use(
  (config) => {
    // 添加Authorization头
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // 添加详细请求日志
    console.groupCollapsed(`%cAPI Request: ${config.method?.toUpperCase()} ${config.url}`, 'color: #2563eb; font-weight: bold;');
    console.log('Headers:', config.headers);
    console.log('Params:', config.params);
    console.log('Data:', config.data);
    console.groupEnd();
    
    return config;
  },
  (error) => {
    console.error('Request Error:', error);
    return Promise.reject(error);
  }
);

// 响应拦截器 - 处理token过期、认证失败和请求重试
api.interceptors.response.use(
  (response) => {
    // 添加详细响应日志
    console.groupCollapsed(`%cAPI Response: ${response.status} ${response.config.url}`, 'color: #16a34a; font-weight: bold;');
    console.log('Status:', response.status);
    console.log('Headers:', response.headers);
    console.log('Data:', response.data);
    console.groupEnd();
    
    return response;
  },
  async (error) => {
    console.error('Response Error:', error);
    
    const originalRequest = error.config;
    
    // 如果是401，清除本地token
    if (error.response?.status === 401) {
      removeToken();
      removeAiToken();
    }
    
    // 请求重试逻辑
    if (!originalRequest._retry) {
      originalRequest._retry = true;
      originalRequest._retryCount = originalRequest._retryCount || 0;
      
      // 检查是否需要重试
      if (
        originalRequest._retryCount < MAX_RETRIES &&
        RETRYABLE_STATUS_CODES.includes(error.response?.status || 0)
      ) {
        originalRequest._retryCount += 1;
        
        console.log(`Retrying request (${originalRequest._retryCount}/${MAX_RETRIES})...`);
        
        // 等待一段时间后重试
        await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
        
        return api(originalRequest);
      }
    }
    
    return Promise.reject(error);
  }
);

// 定义DashboardStats类型 - 根据后端文档调整
export interface DashboardStats {
  anime: number;
  book: number;
  game: number;
  music: number;
  real: number;
}

// 定义收藏和条目类型
export interface Subject {
  id: number;
  name: string;
  name_cn: string;
  type: number;
  cover_url: string;
  summary: string;
  date: string;
  platform?: string;
  eps?: number;
  volumes?: number;
  score?: number;
  rank?: number;
  collection_total?: number;
  tags: string[];
  meta_tags: string[];
  infobox: Record<string, string>;
  rating_details: Record<string, number | string>;
  images: Record<string, string>;
  is_collected?: boolean;
  is_favorited?: boolean;
  collection_info?: CollectionInfo;
}

export interface CollectionInfo {
  subject_id: number;
  status?: string;
  rate?: number;
  comment?: string;
  private: boolean;
  tags: string[];
  updated_at?: string;
}

export interface Collection {
  id: number;
  user_id: number;
  subject_id: number;
  status: number;
  rate: number;
  comment: string;
  tags: string[];
  updated_at: string;
  created_at: string;
  private: boolean;
}

export interface CollectionWithSubject {
  collection: Collection;
  subject: Subject;
}

// 登录/注册 - 根据后端文档添加
export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export async function login(username: string): Promise<LoginResponse> {
  try {
    const response = await api.post<LoginResponse>('/auth/login', {
      username
    });
    // 保存token
    saveToken(response.data.access_token);
    return response.data;
  } catch (error) {
    console.error('Error logging in:', error);
    throw error;
  }
}

// 获取dashboard统计数据 - 根据后端文档调整
export async function fetchDashboardStats(): Promise<DashboardStats> {
  try {
    const response = await api.get<DashboardStats>('/dashboard/stats');
    return response.data;
  } catch (error) {
    console.error('Error fetching dashboard stats:', error);
    // 返回默认值，避免页面崩溃
    return {
      anime: 0,
      book: 0,
      game: 0,
      music: 0,
      real: 0
    };
  }
}

// 同步用户数据 - 根据后端文档调整
export interface SyncResponse {
  message: string;
  username: string;
  sync_count: number;
  subject_type: number;
  source: string;
}

export async function syncUser(source: string, subjectType?: number, data?: unknown[]): Promise<SyncResponse> {
  try {
    const response = await api.post<SyncResponse>('/collections/sync', {
      source,
      subject_type: subjectType,
      data
    }, {
      timeout: 300000 // 设置为 5 分钟 (300000ms)
    });
    return response.data;
  } catch (error) {
    console.error('Error syncing user data:', error);
    throw error;
  }
}

// 搜索条目 - 根据后端文档调整
export async function searchSubjects(
  keyword: string,
  type?: number,
  source: 'local' | 'remote' | 'mixed' = 'mixed',
  limit: number = 20,
  offset: number = 0,
  sort: 'rank' | 'score' | 'date' = 'rank'
): Promise<Subject[]> {
  try {
    const response = await api.get<Subject[]>('/subjects', {
      params: {
        q: keyword,
        source,
        type,
        limit,
        offset,
        sort
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error searching subjects:', error);
    return [];
  }
}

// 获取单个条目详情
export async function getSubjectDetail(
  subjectId: number,
  refresh: boolean = false
): Promise<Subject | null> {
  try {
    const response = await api.get<Subject>(`/subjects/${subjectId}`, {
      params: { refresh }
    });
    return response.data;
  } catch (error) {
    console.error(`Error getting subject ${subjectId} detail:`, error);
    return null;
  }
}

// 获取用户收藏列表 - 根据后端文档调整
export interface CollectionsResponse {
  total: number;
  items: CollectionWithSubject[];
}

export async function getUserCollections(
  subjectType?: number,
  status?: number,
  keyword?: string,
  limit: number = 20,
  offset: number = 0,
  sortBy: string = 'updated_at'
): Promise<CollectionsResponse> {
  try {
    const response = await api.get<CollectionsResponse>('/collections', {
      params: {
        subject_type: subjectType,
        status,
        keyword,
        limit,
        offset,
        sort_by: sortBy
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching user collections:', error);
    return {
      total: 0,
      items: []
    };
  }
}

// 更新或添加收藏 - 根据后端文档调整
export interface CollectionUpdateData {
  status: number;
  rate: number;
  comment: string;
  private: boolean;
  tags: string[];
}

export interface SubjectData {
  name: string;
  name_cn: string;
  type: number;
  cover_url: string;
  release_date: string;
  publish_date: string;
  status?: number;
  rate?: number;
  comment?: string;
  tags: string[];
}

export interface CollectionUpdateResponse {
  subject_id: number;
  updated_at: string;
  status: number;
  rate: number;
  comment: string;
  private: boolean;
  tags: string[];
  subject: Subject | null;
}

export async function updateOrAddCollection(
  subjectId: number,
  collectionData: CollectionUpdateData,
  subjectData?: SubjectData
): Promise<CollectionUpdateResponse> {
  try {
    // 统一调用POST /collections/接口，使用查询参数sid区分更新和创建
    const response = await api.post<CollectionUpdateResponse>(`/collections/`, {
      collection: collectionData,
      subject: subjectData
    }, {
      params: {
        sid: subjectId
      }
    });
    return response.data;
  } catch (error) {
    console.error(`Error updating or adding collection for subject ${subjectId}:`, error);
    throw error;
  }
}

// 修改条目信息
export async function updateSubject(
  subjectId: number,
  updateData: Partial<Subject>
): Promise<Subject | null> {
  try {
    const response = await api.put<Subject>(`/subjects/${subjectId}`, updateData);
    return response.data;
  } catch (error) {
    console.error(`Error updating subject ${subjectId}:`, error);
    return null;
  }
}

// 上传豆瓣数据文件 - 根据后端文档调整
export async function uploadDoubanFile(file: File): Promise<SyncResponse> {
  try {
    // 首先读取文件内容
    const fileContent = await file.text();
    const data = JSON.parse(fileContent);
    
    // 使用后端文档中的同步接口
    return syncUser('douban', undefined, data);
  } catch (error) {
    console.error('Error uploading Douban file:', error);
    throw error;
  }
}

// 获取当前用户信息 - 根据后端文档调整
export interface UserInfo {
  id: number;
  username: string;
  nickname: string;
  email: string | null;
  avatar_url: string | null;
  bangumi_id: string | null;
  sign: string;
  created_at: string;
}

export async function getCurrentUserInfo(): Promise<UserInfo | null> {
  try {
    const response = await api.get<UserInfo>('/users/me');
    return response.data;
  } catch (error) {
    console.error('Error fetching current user info:', error);
    return null;
  }
}

// Batch import collections - 根据后端文档调整
export interface ImportItem {
  subject: Subject;
  collection: CollectionUpdateData;
}

export async function batchImportCollections(items: ImportItem[]): Promise<SyncResponse> {
  try {
    // 这里可以根据实际情况调整，可能需要分批导入
    // 目前暂时使用现有的同步接口，后续可以根据需要扩展
    const response = await api.post<SyncResponse>('/collections/sync', {
      source: 'manual',
      data: items
    });
    return response.data;
  } catch (error) {
    console.error('Error batch importing collections:', error);
    throw error;
  }
}

// Bangumi用户信息接口
export interface BangumiUser {
  id: number;
  username: string;
  nickname: string;
  sign: string;
  bangumi_id?: string;
  avatar: {
    large: string;
    medium: string;
    small: string;
  };
}

export async function fetchBangumiUser(username: string): Promise<BangumiUser | null> {
  try {
    const response = await axios.get(`https://api.bgm.tv/v0/users/${username}`);
    
    return {
      id: response.data.id,
      username: response.data.username,
      nickname: response.data.nickname,
      sign: response.data.sign,
      bangumi_id: response.data.id?.toString(),
      avatar: response.data.avatar
    };
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      console.warn(`Bangumi user "${username}" not found`);
      return null;
    }
    throw error;
  }
}

// 定义Grid相关类型
export interface GridSlot {
  subject: Subject | null;
  type: 'best' | 'worst';
}

export interface GridState {
  [category: string]: {
    best: GridSlot;
    worst: GridSlot;
  };
}

// 辅助方法：将Grid数据转换为ImportItem数组
export function gridStateToImportItems(gridState: GridState): ImportItem[] {
  const items: ImportItem[] = [];
  
  for (const category in gridState) {
    const categoryData = gridState[category];
    
    if (categoryData.best.subject) {
      items.push({
        subject: categoryData.best.subject,
        collection: {
          status: 2, // 看过
          rate: 10, // 最佳评分
          comment: '',
          private: false,
          tags: [category]
        }
      });
    }

    if (categoryData.worst.subject) {
      items.push({
        subject: categoryData.worst.subject,
        collection: {
          status: 2, // 看过
          rate: 1, // 最差评分
          comment: '',
          private: false,
          tags: [category]
        }
      });
    }
  }
  
  return items;
}

// 手动添加收藏 - 使用updateOrAddCollection方法实现
// 可以保留原有的方法签名，内部调用新的updateOrAddCollection
export interface ManualCollectionData {
  subject_id?: number;
  name: string;
  type: number;
  status: number;
  cover_url?: string;
  rate: number;
  comment?: string;
  release_date?: string;
  publish_date?: string;
  tags?: string;
}

export async function createManualCollection(data: ManualCollectionData): Promise<CollectionUpdateResponse> {
  try {
    if (data.subject_id) {
      // 如果有subject_id，直接更新收藏
      return updateOrAddCollection(data.subject_id, {
        status: data.status,
        rate: data.rate,
        comment: data.comment || '',
        private: false,
        tags: data.tags ? data.tags.split(/[,，]/).map(t => t.trim()).filter(Boolean) : []
      });
    } else {
      // 没有subject_id，需要先创建subject，然后添加收藏
      // 这里需要根据后端实际实现调整
      throw new Error('Creating subject is not supported directly, please use search first');
    }
  } catch (error) {
    console.error('Error creating manual collection:', error);
    throw error;
  }
}

export default api;
