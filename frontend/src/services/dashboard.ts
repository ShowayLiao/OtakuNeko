import { request } from './client';

// 仪表板统计数据
export interface DashboardStats {
  anime: number;
  books: number;
  music: number;
  games: number;
  real: number;
  total: number;
}

// 仪表板服务
export const dashboardService = {
  // 获取用户统计数据
  async getStats(): Promise<DashboardStats> {
    return request<DashboardStats>('/dashboard/stats');
  },
};
