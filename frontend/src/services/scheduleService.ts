import { request } from './client';
import { BangumiItem } from './bangumiService';

// 定义排班记录的基础接口
export interface ScheduleBase {
  id?: number;
  title: string;
  start_time: string;
  end_time: string;
  day_of_week: number;
  status?: string;
  type?: string;
  description?: string;
}

// 获取收藏数据并转换为 BangumiItem 格式
export const getCollections = async (params?: {
  subject_type?: number;
  status?: number;
}): Promise<BangumiItem[]> => {
  try {
    console.log('scheduleService.getCollections: 调用 API，参数:', params);
    
    // 构建查询参数
    const urlParams = new URLSearchParams();
    if (params?.subject_type !== undefined) urlParams.append('subject_type', params.subject_type.toString());
    if (params?.status !== undefined) urlParams.append('status', params.status.toString());

    const queryString = urlParams.toString();
    const endpoint = `/collections${queryString ? `?${queryString}` : ''}`;
    
    // 调用后端 API 获取收藏数据
    const response = await request<any>(endpoint, {
      method: 'GET'
    });
    console.log('scheduleService.getCollections: API 响应:', response);
    
    // 转换数据格式为 BangumiItem[]
    const items: BangumiItem[] = (response?.items || []).map((collectionItem: any) => {
      return {
        collection: collectionItem.collection || null,
        subject: collectionItem.subject || null,
        watch_day: null,
        watch_time: null,
        watch_type: null,
        duration: null
      };
    });
    
    return items;
  } catch (error) {
    console.error('获取收藏数据失败:', error);
    throw error;
  }
};

// 定义批量 upsert 的请求数据结构
export interface ScheduleUpsertList {
  items: ScheduleBase[];
}

// 定义后端返回的排班记录结构
export interface ScheduleRead extends ScheduleBase {
  id: number;
  user_id: number;
  created_at: string;
  updated_at: string;
}

// 定义后端返回的批量 upsert 响应结构
export interface ScheduleReadList {
  items: ScheduleRead[];
  total: number;
}

// 批量 upsert 排班记录
export const bulkUpsertSchedules = async (schedules: ScheduleBase[]): Promise<ScheduleReadList> => {
  try {
    const response = await request<ScheduleReadList>('/schedules/bulk-upsert', {
      method: 'POST',
      body: JSON.stringify({ items: schedules })
    });
    return response;
  } catch (error) {
    console.error('批量 upsert 排班记录失败:', error);
    throw error;
  }
};
