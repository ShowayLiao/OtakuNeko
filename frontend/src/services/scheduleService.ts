import { request } from './client';
import { BangumiItem, WatchType } from './bangumiService';

interface CollectionResponseItem {
  collection?: BangumiItem['collection'];
  subject?: BangumiItem['subject'];
}

interface CollectionResponse {
  items?: CollectionResponseItem[];
}

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
  keyword?: string;
  signal?: AbortSignal;
}): Promise<BangumiItem[]> => {
  try {
    const urlParams = new URLSearchParams();
    if (params?.subject_type !== undefined) urlParams.append('subject_type', params.subject_type.toString());
    if (params?.status !== undefined) urlParams.append('status', params.status.toString());
    if (params?.keyword !== undefined) urlParams.append('keyword', params.keyword);

    const queryString = urlParams.toString();
    const endpoint = `/collections/${queryString ? `?${queryString}` : ''}`;
    
    // 调用后端 API 获取收藏数据
    const response = await request<CollectionResponse>(endpoint, {
      method: 'GET',
      signal: params?.signal,
    });
    
    let items: BangumiItem[] = (response.items || []).filter((item) => item.subject).map((collectionItem) => {
      return {
        collection: collectionItem.collection || null,
        subject: collectionItem.subject!,
        watch_day: undefined,
        watch_time: undefined,
        watch_type: undefined,
        duration: undefined
      };
    });
    
    // 如果收藏搜索结果为空，且有关键词或类型过滤，则调用 subjects 接口
    if (items.length === 0 && (params?.keyword || params?.subject_type !== undefined)) {
      const subjectsParams = new URLSearchParams();
      if (params?.keyword !== undefined) subjectsParams.append('q', params.keyword);
      if (params?.subject_type !== undefined) subjectsParams.append('type', params.subject_type.toString());
      
      const subjectsQueryString = subjectsParams.toString();
      const subjectsEndpoint = `/subjects${subjectsQueryString ? `?${subjectsQueryString}` : ''}`;
      
      // 调用 subjects 接口
      const subjectsResponse = await request<CollectionResponse>(subjectsEndpoint, {
        method: 'GET',
        signal: params?.signal,
      });
      
      const subjectsItems: BangumiItem[] = (subjectsResponse.items || []).filter((item) => item.subject).map((subjectItem) => {
        return {
          collection: subjectItem.collection || null,
          subject: subjectItem.subject!,
          watch_day: undefined,
          watch_time: undefined,
          watch_type: undefined,
          duration: undefined
        };
      });
      
      items = subjectsItems;
    }
    
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
  subject?: BangumiItem['subject'];
  collection?: BangumiItem['collection'];
  schedule?: { day_of_week?: number; start_time?: string; duration?: number; watch_type?: number };
}

// 定义后端返回的批量 upsert 响应结构
export interface ScheduleReadList {
  items: ScheduleRead[];
  total: number;
}

// 将 BangumiItem 转换为后端 API 要求的格式
export const convertBangumiItemsToSchedules = (items: BangumiItem[]): ScheduleBase[] => {
  const userId = 1; // 暂时硬编码，后续应该从认证系统获取
  
  const convertedItems = items.map(item => {
    // 确保必要字段存在且格式正确
    const source = item.subject?.source || 'bangumi';
    const sourceId = item.subject?.source_id || '';
    const watchDay = item.watch_day ?? 0;
    const watchTime = item.watch_time || '00:00';
    
    const convertedItem = {
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
    
    return convertedItem;
  }).filter(item => item.source_id);
  
  return convertedItems;
};

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

// 将后端返回的 UnifiedScheduleList 转换为 BangumiItem[] 格式
export const convertSchedulesToBangumiItems = (schedulesData: ScheduleReadList): BangumiItem[] => {
  if (!schedulesData || !schedulesData.items) {
    return [];
  }
  
  return schedulesData.items.filter((item) => {
    // 检查 subject 是否存在，以及 air_time 和 air_weekday 是否不为 null
    if (!item.subject) {
      return false;
    }
    // 当 air_time 或 air_weekday 为 null 时跳过该 item
    if (item.subject.air_time === null || item.subject.air_weekday === null) {
      return false;
    }
    return true;
  }).map((item) => {
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
    const response = await request<ScheduleReadList>('/schedules', {
      method: 'GET'
    });
    
    const bangumiItems = convertSchedulesToBangumiItems(response);
    
    return bangumiItems;
  } catch (error) {
    console.error('获取排班记录失败:', error);
    throw error;
  }
};

// 删除所有排班记录
export const deleteAllSchedules = async (): Promise<{ status: string; message: string }> => {
  try {
    const response = await request<{ status: string; message: string }>('/schedules/all', {
      method: 'DELETE'
    });
    
    return response;
  } catch (error) {
    console.error('删除所有排班记录失败:', error);
    throw error;
  }
};
