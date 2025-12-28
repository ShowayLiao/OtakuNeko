import axios from 'axios';

// 创建axios实例
const api = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  timeout: 10000, // 请求超时时间
  headers: {
    'Content-Type': 'application/json',
  },
});

// 定义DashboardStats类型
export interface DashboardStats {
  total_subjects: number;
  total_collections: number;
  system_status: string;
  recent_activity: RecentActivityItem[];
}

export interface RecentActivityItem {
  id: string;
  user_id: number;
  subject_id: number;
  subject_name: string;
  subject_type: number;
  collection_type: number;
  updated_at: string;
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
  rating_details: Record<string, any>;
  images: Record<string, any>;
  is_collected?: boolean;
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
}

export interface CollectionWithSubject {
  collection: Collection;
  subject: Subject;
}

// 获取dashboard统计数据
export async function fetchDashboardStats(): Promise<DashboardStats> {
  try {
    const response = await api.get<DashboardStats>('/dashboard/stats');
    return response.data;
  } catch (error) {
    console.error('Error fetching dashboard stats:', error);
    // 返回默认值，避免页面崩溃
    return {
      total_subjects: 0,
      total_collections: 0,
      system_status: 'Running',
      recent_activity: [],
    };
  }
}

// 同步用户数据
export async function syncUser(username: string, subjectType?: number): Promise<void> {
  try {
    const response = await api.post('/collections/sync', null, {
      params: {
        username: username,
        subject_type: subjectType
      },
      timeout: 300000 // 设置为 5 分钟 (300000ms)
    });
    return response.data;
  } catch (error) {
    console.error('Error syncing user data:', error);
    throw error;
  }
}

// 获取用户收藏数量
export async function getUserCollectionCount(username: string, subjectType: number): Promise<number> {
  try {
    console.log('[API] getUserCollectionCount 调用:', { username, subjectType });
    
    const response = await api.get('/collections/count', {
      params: { username, subject_type: subjectType }
    });
    
    console.log('[API] getUserCollectionCount 响应:', response.data);
    
    return response.data.count;
  } catch (error) {
    if (error && typeof error === 'object' && 'response' in error) {
      const axiosError = error as { response?: { status?: number; data?: any }; config?: { url?: string; params?: any } };
      
      console.error('[API] getUserCollectionCount 错误:', {
        status: axiosError.response?.status,
        data: axiosError.response?.data,
        url: axiosError.config?.url,
        params: axiosError.config?.params
      });
      
      if (axiosError.response?.status === 422) {
        console.error('[API] 参数验证失败:', axiosError.response.data);
      }
    } else {
      console.error('[API] getUserCollectionCount 未知错误:', error);
    }
    
    return 0;
  }
}

// 搜索条目（在所有 Subject 中搜索）
export interface BangumiSearchResponse {
  data: BangumiSubject[];
  total: number;
  limit: number;
  offset: number;
}

export interface BangumiSubject {
  id: number;
  name: string;
  name_cn?: string;
  type: number;
  images?: {
    large?: string;
    common?: string;
    small?: string;
    grid?: string;
  };
  summary?: string;
  date?: string;
  platform?: string;
  eps?: number;
  volumes?: number;
  score?: number;
  rank?: number;
  collection?: {
    doing?: number;
    collect?: number;
    wish?: number;
    dropped?: number;
    on_hold?: number;
  };
}

export async function searchBangumiSubjects(keyword?: string, type?: number): Promise<Subject[]> {
  try {
    const response = await api.post<BangumiSearchResponse>('/subjects/search-bangumi', null, {
      params: { keyword, type }
    });
    
    const bangumiSubjects = response.data.data || [];
    
    return bangumiSubjects.map(bangumiSubject => ({
      id: bangumiSubject.id,
      name: bangumiSubject.name,
      name_cn: bangumiSubject.name_cn || '',
      type: bangumiSubject.type,
      cover_url: bangumiSubject.images?.common || bangumiSubject.images?.large || '',
      summary: bangumiSubject.summary || '',
      date: bangumiSubject.date || '',
      platform: bangumiSubject.platform,
      eps: bangumiSubject.eps,
      volumes: bangumiSubject.volumes,
      score: bangumiSubject.score,
      rank: bangumiSubject.rank,
      collection_total: bangumiSubject.collection?.collect,
      tags: [],
      meta_tags: [],
      infobox: {},
      rating_details: {},
      images: bangumiSubject.images || {}
    }));
  } catch (error) {
    console.error('Error searching Bangumi subjects:', error);
    return [];
  }
}

export async function searchSubjects(keyword?: string, type?: number): Promise<Subject[]> {
  try {
    const response = await api.get('/subjects', {
      params: { keyword, type }
    });
    return response.data;
  } catch (error) {
    console.error('Error searching subjects:', error);
    return [];
  }
}

export async function searchMixedSubjects(keyword?: string, type?: number, username?: string): Promise<Subject[]> {
  try {
    const response = await api.get('/subjects/search/mixed', {
      params: { keyword, type, username }
    });
    return response.data.data || [];
  } catch (error) {
    console.error('Error searching mixed subjects:', error);
    return [];
  }
}

// 获取用户收藏列表
export async function getUserCollections(username: string, keyword?: string, type?: number): Promise<CollectionWithSubject[]> {
  try {
    const response = await api.get('/collections', {
      params: { username, keyword, type }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching user collections:', error);
    // 返回模拟数据用于测试
    return [
      {
        collection: {
          id: 1,
          user_id: 1,
          subject_id: 1,
          status: 2,
          rate: 10,
          comment: "神作！",
          tags: ["科幻", "悬疑"],
          updated_at: "2024-01-01T00:00:00Z",
          created_at: "2024-01-01T00:00:00Z"
        },
        subject: {
          id: 1,
          name: "Steins;Gate",
          name_cn: "命运石之门",
          type: 2,
          cover_url: "https://example.com/steinsgate.jpg",
          summary: "这是一部关于时间旅行的科幻作品...",
          date: "2011-04-06",
          eps: 24,
          score: 9.5,
          tags: ["科幻", "悬疑"],
          meta_tags: [],
          infobox: {},
          rating_details: {
            score: 9.5,
            rank: 1
          },
          images: {}
        }
      },
      {
        collection: {
          id: 2,
          user_id: 1,
          subject_id: 2,
          status: 2,
          rate: 9,
          comment: "很有趣",
          tags: ["冒险", "奇幻"],
          updated_at: "2024-01-02T00:00:00Z",
          created_at: "2024-01-02T00:00:00Z"
        },
        subject: {
          id: 2,
          name: "Hunter x Hunter",
          name_cn: "全职猎人",
          type: 2,
          cover_url: "https://example.com/hunterxhunter.jpg",
          summary: "这是一部关于冒险和成长的作品...",
          date: "2011-10-02",
          eps: 148,
          score: 9.2,
          tags: ["冒险", "奇幻"],
          meta_tags: [],
          infobox: {},
          rating_details: {
            score: 9.2,
            rank: 5
          },
          images: {}
        }
      }
    ];
  }
}

// 上传豆瓣数据文件
export async function uploadDoubanFile(file: File, username: string): Promise<{ message: string; username: string; import_count: number }> {
  try {
    const formData = new FormData();
    formData.append('file', file);

    console.log('[DEBUG API] uploadDoubanFile 调用:');
    console.log('[DEBUG API] - username:', username);
    console.log('[DEBUG API] - file:', file.name, file.size, 'bytes');
    console.log('[DEBUG API] - 完整URL:', `http://localhost:8000/api/v1/collections/sync/douban?username=${encodeURIComponent(username)}`);

    const response = await api.post<{ message: string; username: string; import_count: number }>('/collections/sync/douban', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params: {
        username: username
      },
      timeout: 300000, // 设置为 5 分钟 (300000ms)
    });
    
    console.log('[DEBUG API] 响应成功:', response.data);
    return response.data;
  } catch (error) {
    console.error('Error uploading Douban file:', error);
    throw error;
  }
}

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

export interface ImportItem {
  subject: Subject;
  collection: {
    user_id: number;
    subject_id: number;
    status: number;
    rate: number;
    comment: string;
    tags: string[];
  };
}

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

export interface LocalUserRegisterRequest {
  username: string;
  bangumi_id?: number;
  avatar?: string;
}

export interface LocalUserRegisterResponse {
  id: number;
  username: string;
  email?: string;
  avatar_url?: string;
  bangumi_id?: number;
  created_at: string;
}

export async function registerLocalUser(data: LocalUserRegisterRequest): Promise<LocalUserRegisterResponse> {
  try {
    const response = await api.post<LocalUserRegisterResponse>('/users/register-local', data);
    return response.data;
  } catch (error) {
    console.error('Error registering local user:', error);
    throw error;
  }
}

export async function batchImportCollections(items: ImportItem[], username: string): Promise<{ message: string; imported_count: number }> {
  try {
    const response = await api.post<{ message: string; imported_count: number }>('/collections/batch', items, {
      params: { username }
    });
    return response.data;
  } catch (error) {
    console.error('Error batch importing collections:', error);
    throw error;
  }
}

export async function getUserInfo(username: string): Promise<BangumiUser | null> {
  try {
    const response = await api.get<{
      id: number;
      username: string;
      email?: string;
      avatar_url?: string;
      bangumi_id?: string;
      sign?: string;
      created_at: string;
    }>('/users/info', {
      params: { username }
    });
    
    return {
      id: response.data.id,
      username: response.data.username,
      nickname: response.data.username,
      sign: response.data.sign || '',
      avatar: {
        large: response.data.avatar_url || '',
        medium: response.data.avatar_url || '',
        small: response.data.avatar_url || ''
      }
    };
  } catch (error) {
    console.error('Error fetching user info:', error);
    return null;
  }
}

export interface LocalUserCheckResponse {
  found: boolean;
  user?: {
    id: number;
    username: string;
    nickname: string;
    email?: string;
    avatar_url?: string;
    bangumi_id?: number;
    sign: string;
    created_at?: string;
  };
}

export async function checkLocalUser(username: string): Promise<LocalUserCheckResponse> {
  try {
    const response = await api.get<LocalUserCheckResponse>('/users/check', {
      params: { username }
    });
    
    return response.data;
  } catch (error) {
    console.error('Error checking local user:', error);
    return { found: false };
  }
}

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

export async function createManualCollection(data: ManualCollectionData, username: string): Promise<{ message: string; subject_id: number; collection_id: number }> {
  try {
    const response = await api.post<{ message: string; subject_id: number; collection_id: number }>('/collections/manual', data, {
      params: { username }
    });
    return response.data;
  } catch (error) {
    console.error('Error creating manual collection:', error);
    throw error;
  }
}

export default api;
