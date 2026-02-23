import { request } from './client';

// 观看类型枚举
export enum WatchType {
  MEAL = 1,      // 饭点
  LEISURE = 2,   // 闲暇
  LONG_GRASS = 3, // 长草
  NEW = 4        // 新番
}

// 定义 Bangumi 日历数据类型
export interface BangumiItem {
  id: string; // 唯一标识符
  title: string; // 标题
  source: string; // 数据来源
  source_id: string; // 数据来源ID
  day_of_week: number; // 星期几（0-6，周日到周六）
  start_time: string; // 放送时间
  watch_day?: number; // 观看星期几
  watch_time?: string; // 观看时间
  duration?: number; // 观看周期
  watch_type?: WatchType; // 观看类型
  user_id: number; // 用户ID
  image?: string; // 封面图片
  images?: {
    common: string;
    large: string;
    medium: string;
    small: string;
  }; // 图片集合
  air_weekday?: number | null; // 放送星期几
  category?: 'Meal' | 'Backlog' | 'Reading' | 'New'; // 分类
  description?: string; // 描述
  span?: number; // 占据列数
}

// 后端返回的数据结构
interface BangumiCalendarDay {
  weekday: {
    en: string;
    ja: string;
    cn: string;
    id: number;
  };
  items: Array<{
    id: number;
    name: string;
    name_cn: string | null;
    summary: string | null;
    air_date: string | null;
    air_weekday: number | null;
  }>;
}

// 获取 Bangumi 日历数据
export const getBangumiCalendar = async (): Promise<BangumiItem[]> => {
  try {
    // 调用后端 API，后端返回的是 BangumiCalendarDay[] 格式
    const response = await request<BangumiCalendarDay[]>('/bangumi/calendar');
    
    // 转换数据格式，确保符合前端组件的要求
    const items: BangumiItem[] = [];
    
    // 遍历每天的数据
    response.forEach(day => {
      // 遍历当天的所有番剧
      day.items.forEach((item, index) => {
        // 计算星期几（后端返回的是 1-7，需要转换为 0-6，0=周日，1=周一，...，6=周六）
        const day_of_week = day.weekday.id === 7 ? 0 : day.weekday.id;
        
        // 提取时间信息
        let start_time = '';
        if (item.air_date) {
          // 尝试从 air_date 中提取时间
          const timeMatch = item.air_date.match(/\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2})/);
          if (timeMatch) {
            start_time = timeMatch[1];
          }
        }
        
        // 创建前端需要的 BangumiItem
        items.push({
          id: item.id.toString() || `bangumi-${day.weekday.id}-${index}`,
          title: item.name_cn || item.name,
          source: 'bangumi',
          source_id: item.id.toString(),
          day_of_week: day_of_week,
          start_time: start_time,
          user_id: 1, // 暂时使用默认用户ID
        });
      });
    });
    
    return items;
  } catch (error) {
    console.error('获取 Bangumi 日历数据失败:', error);
    throw error;
  }
};

// 后端返回的 /sync-bangumi 数据结构
interface UnifiedSubject {
  id: number;
  source: string;
  source_id: string;
  name: string;
  name_cn: string;
  type: number;
  summary: string | null;
  date: string;
  platform: string;
  eps: number | null;
  volumes: number | null;
  images: {
    common: string;
    large: string;
    medium: string;
    small: string;
  };
  image: string;
  tags: Array<{
    name: string;
    count: number;
  }>;
  meta_tags: string[];
  infobox: Array<{
    key: string;
    value: string;
  }>;
  rating: {
    score: number;
    count: number;
  };
  collection: {
    total: number;
  };
  series: boolean;
  locked: boolean;
  nsfw: boolean;
  air_time: string | null;
  air_weekday: number | null;
  last_sync: string | null;
}

interface UnifiedCollectionSubjectResponse {
  collection: null | any;
  subject: UnifiedSubject;
}

interface SyncBangumiResponse {
  total: number;
  items: UnifiedCollectionSubjectResponse[];
}

// 同步 Bangumi 日历数据
export const syncBangumiCalendar = async (): Promise<BangumiItem[]> => {
  try {
    // 调用后端 API，后端返回的是 UnifiedList 格式，使用 POST 方法
    const response = await request<SyncBangumiResponse>('/schedules/sync-bangumi', {
      method: 'POST'
    });
    
    // 转换数据格式，确保符合前端组件的要求
    const items: BangumiItem[] = [];
    
    // 遍历所有番剧
    response.items.forEach((item, index) => {
      // 确保 subject 存在
      if (!item.subject) return;
      
      const subject = item.subject;
      
      // 提取时间信息并转换为客户端时区
      let start_time = '';
      // 默认先用后端给的 air_weekday 兜底 (如果是7转成0)
      let day_of_week = subject.air_weekday ? (subject.air_weekday === 7 ? 0 : subject.air_weekday) : 0;

      if (subject.air_time) {
        try {
          // 补齐 'Z'，确保浏览器将其解析为 UTC 时间
          const timeStr = subject.air_time.endsWith('Z')
            ? subject.air_time
            : `${subject.air_time}Z`;
            
          const utcDate = new Date(timeStr);

          // 确保日期解析成功，不是 Invalid Date
          if (!isNaN(utcDate.getTime())) {
            // getHours() 和 getMinutes() 自动转换到本地时区
            const localHour = utcDate.getHours().toString().padStart(2, '0');
            const localMinute = utcDate.getMinutes().toString().padStart(2, '0');
            start_time = `${localHour}:${localMinute}`;
            
            // ✨ 核心修改：利用本地化后的 Date 对象直接获取星期几，覆盖后端的 weekday
            // utcDate.getDay() 返回的就是 0-6（0代表周日），完美契合你的设定
            day_of_week = utcDate.getDay();
          }
        } catch (error) {
          console.error('时间解析失败:', subject.air_time, error);
        }
      }

      // 创建前端需要的 BangumiItem
      items.push({
        id: subject.source_id || `bangumi-${index}`,
        title: subject.name_cn || subject.name,
        source: 'bangumi',
        source_id: subject.source_id || subject.id.toString(),
        day_of_week: day_of_week, // 这里的 day 已经是完美对齐本地时区的了
        start_time: start_time,
        watch_day: day_of_week,   // watch_day 也同步更新
        watch_type: WatchType.NEW,
        watch_time: start_time,   // watch_time 也同步更新
        user_id: 1,
        image: subject.image || subject.images?.common || '',
        images: subject.images,
        air_weekday: subject.air_weekday
      });
    });
    
    return items;
  } catch (error) {
    console.error('同步 Bangumi 日历数据失败:', error);
    throw error;
  }
};
