import { request } from './client';

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
