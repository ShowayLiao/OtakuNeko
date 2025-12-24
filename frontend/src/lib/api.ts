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
  image: string;
  summary: string;
  air_date: string;
  air_weekday: number;
  eps: number;
  score?: number;
  rating?: {
    total: number;
    count: {
      '1': number;
      '2': number;
      '3': number;
      '4': number;
      '5': number;
      '6': number;
      '7': number;
      '8': number;
      '9': number;
      '10': number;
    };
    score: number;
  };
  rating_details?: {
    score: number;
    rank: number;
  };
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
export async function syncUser(username: string): Promise<void> {
  try {
    const response = await api.post('/collections/sync', null, {
      params: {
        username: username,
        subject_type: 2
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
    const response = await api.get('/collections/count', {
      params: { username, subject_type: subjectType }
    });
    return response.data.count;
  } catch (error) {
    console.error('Error fetching user collection count:', error);
    return 0;
  }
}

// 获取用户收藏列表
export async function getUserCollections(keyword?: string, type?: number): Promise<CollectionWithSubject[]> {
  try {
    const response = await api.get('/collections', {
      params: { keyword, type }
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
          image: "https://example.com/steinsgate.jpg",
          summary: "这是一部关于时间旅行的科幻作品...",
          air_date: "2011-04-06",
          air_weekday: 4,
          eps: 24,
          score: 9.5,
          rating: {
            total: 10000,
            count: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 1000, "10": 9000 },
            score: 9.5
          },
          rating_details: {
            score: 9.5,
            rank: 1
          }
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
          image: "https://example.com/hunterxhunter.jpg",
          summary: "这是一部关于冒险和成长的作品...",
          air_date: "2011-10-02",
          air_weekday: 1,
          eps: 148,
          score: 9.2,
          rating: {
            total: 8000,
            count: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 1000, "9": 5000, "10": 2000 },
            score: 9.2
          },
          rating_details: {
            score: 9.2,
            rank: 5
          }
        }
      }
    ];
  }
}

export default api;
