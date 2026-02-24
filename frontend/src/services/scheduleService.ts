import { request } from './client';
import { BangumiItem, WatchType } from './bangumiService';

// 定义排班记录的基础接口
export interface ScheduleBase {
  id?: number;
  source: string;
  source_id: string;
  day_of_week: number;
  start_time: string;
  watch_day?: number;
  watch_time?: string;
  duration?: number;
  watch_type?: number;
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

// 将 BangumiItem 转换为后端 API 要求的格式
export const convertBangumiItemsToSchedules = (items: any[]): any[] => {
  const userId = 1; // 暂时硬编码，后续应该从认证系统获取
  
  return items.map(item => {
    // 确保必要字段存在且格式正确
    const source = item.subject?.source || 'bangumi';
    const sourceId = item.subject?.source_id || '';
    const watchDay = item.watch_day ?? 0;
    const watchTime = item.watch_time || '00:00';
    
    // 打印转换前的原始item，方便调试
    console.log("转换前的原始item:", item);
    
    return {
      source,
      source_id: sourceId,
      day_of_week: watchDay,
      start_time: watchTime,
      watch_day: watchDay,
      watch_time: watchTime,
      duration: item.duration || 1,
      watch_type: item.watch_type != null ? item.watch_type : 4, // 4 = NEW
      user_id: userId
    };
  }).filter(item => item.source_id); // 过滤掉没有 source_id 的项
};

// 批量 upsert 排班记录
export const bulkUpsertSchedules = async (schedules: any[]): Promise<ScheduleReadList> => {
  try {
    console.log('发送到后端的数据:', { items: schedules });
    
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

// 将后端返回的 UnifiedScheduleList 转换为 BangumiItem[] 格式
export const convertSchedulesToBangumiItems = (schedulesData: any): BangumiItem[] => {
  if (!schedulesData || !schedulesData.items) {
    return [];
  }
  
  return schedulesData.items.map((item: any) => {
    // 构建 BangumiItem 对象
    const bangumiItem: BangumiItem = {
      collection: item.collection || null,
      subject: item.subject || {
        id: 0,
        name: '未知标题',
        name_cn: '',
        type: 2, // 默认动画类型
        source: 'bangumi',
        source_id: '',
        images: {},
        image: ''
      },
      watch_day: item.schedule?.day_of_week || 0,
      watch_time: item.schedule?.start_time || '',
      duration: item.schedule?.duration || 1,
      watch_type: item.schedule?.watch_type || WatchType.NEW
    };
    
    return bangumiItem;
  });
};

// 获取排班记录列表并转换为 BangumiItem[]
export const getSchedules = async (): Promise<BangumiItem[]> => {
  try {
    console.log('调用 getSchedules API');
    
    const response = await request<any>('/schedules', {
      method: 'GET'
    });
    
    console.log('getSchedules API 响应:', response);
    
    // 转换数据格式
    const bangumiItems = convertSchedulesToBangumiItems(response);
    console.log('转换后的 BangumiItems:', bangumiItems);
    
    return bangumiItems;
  } catch (error) {
    console.error('获取排班记录失败:', error);
    throw error;
  }
};

// 删除所有排班记录
export const deleteAllSchedules = async (): Promise<{ status: string; message: string }> => {
  try {
    console.log('调用 deleteAllSchedules API');
    
    const response = await request<{ status: string; message: string }>('/schedules/all', {
      method: 'DELETE'
    });
    
    console.log('deleteAllSchedules API 响应:', response);
    return response;
  } catch (error) {
    console.error('删除所有排班记录失败:', error);
    throw error;
  }
};
