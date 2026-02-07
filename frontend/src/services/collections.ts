import { request } from './client';

// 同步收藏请求参数
export interface CollectionSyncRequest {
  subject_type?: string;
  limit?: number;
  offset?: number;
}

// 同步收藏响应
export interface CollectionSyncResponse {
  message: string;
  username: string;
  sync_count: number;
  import_count: number;
  subject_type?: string;
  source: string;
}

// 收藏项类型
export interface CollectionItem {
  id: string;
  title: string;
  cover: string;
  type: string;
  status: string;
  score: number;
  eps?: number;
  source: string;
  source_id: string;
}

// 收藏列表响应
export interface CollectionListResponse {
  total: number;
  items: CollectionItem[];
}

// 获取收藏列表请求参数
export interface GetCollectionsRequest {
  subject_type?: number;
  status?: number;
  keyword?: string;
  limit?: number;
  offset?: number;
  sort_by?: string;
}

// 豆瓣 JSON 上传请求参数
export interface DoubanUploadRequest {
  subject_type?: string;
  data: any[];
}

// 收藏服务
export const collectionService = {
  // 同步用户的 Bangumi 收藏数据到本地数据库
  async syncBgm(data: CollectionSyncRequest = {}): Promise<CollectionSyncResponse> {
    return request<CollectionSyncResponse>('/collections/sync/bgm', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // 获取收藏列表
  async getCollections(data: GetCollectionsRequest = {}): Promise<CollectionListResponse> {
    // 构建查询参数
    const params = new URLSearchParams();
    if (data.subject_type !== undefined) params.append('subject_type', data.subject_type.toString());
    if (data.status !== undefined) params.append('status', data.status.toString());
    if (data.keyword) params.append('keyword', data.keyword);
    if (data.limit) params.append('limit', data.limit.toString());
    if (data.offset) params.append('offset', data.offset.toString());
    if (data.sort_by) params.append('sort_by', data.sort_by);

    const queryString = params.toString();
    const endpoint = `/collections${queryString ? `?${queryString}` : ''}`;

    return request<CollectionListResponse>(endpoint, {
      method: 'GET',
    });
  },

  // 上传豆瓣 JSON 数据
  async uploadDouban(data: DoubanUploadRequest): Promise<CollectionSyncResponse> {
    return request<CollectionSyncResponse>('/collections/upload/douban', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
