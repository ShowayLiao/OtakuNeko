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

// 收藏服务
export const collectionService = {
  // 同步用户的 Bangumi 收藏数据到本地数据库
  async syncBgm(data: CollectionSyncRequest = {}): Promise<CollectionSyncResponse> {
    return request<CollectionSyncResponse>('/collections/sync/bgm', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
