// 定义搜索相关的类型接口
interface Subject {
  id: number;
  date: string;
  images?: {
    small?: string;
    grid?: string;
    large?: string;
    medium?: string;
    common?: string;
  };
  name: string;
  name_cn: string;
  short_summary: string;
  tags?: Array<{
    name: string;
    count: number;
    total_cont: number;
  }>;
  score: number;
  type: number;
  eps: number;
  volumes: number;
  source: string;
  image?: string;
  source_id?: number;
  rating?: {
    score: number;
  };
  summary?: string;
}

interface Collection {
  type?: number;
  rate?: number;
  comment?: string;
  vol_status?: number;
  ep_status?: number;
  tags?: string[];
}

interface SearchResult {
  subject: Subject;
  collection?: Collection;
}

interface SearchResponse {
  items: SearchResult[];
}

// 搜索参数接口
interface SearchParams {
  keyword: string;
  offset?: number;
  limit?: number;
}

// 搜索服务
class SearchService {
  // 基础 API URL
  private baseUrl = 'http://localhost:8000/api/v1';

  /**
   * 搜索条目
   * @param params 搜索参数
   * @returns 搜索结果
   */
  async searchSubjects(params: SearchParams): Promise<SearchResult[]> {
    const {
      keyword,
      offset = 0,
      limit = 10
    } = params;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${this.baseUrl}/subjects/?q=${encodeURIComponent(keyword)}&limit=${limit}&offset=${offset}`,
        {
          method: 'GET',
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`);
      }

      const data: SearchResponse = await response.json();
      return data.items || [];
    } catch (error) {
      console.error('Search error:', error);
      throw error;
    }
  }

  /**
   * 加载更多搜索结果
   * @param params 搜索参数
   * @returns 搜索结果
   */
  async loadMoreSubjects(params: SearchParams): Promise<SearchResult[]> {
    return this.searchSubjects(params);
  }
}

// 导出单例实例
export const searchService = new SearchService();

// 导出类型
export type { Subject, Collection, SearchResult, SearchParams };
