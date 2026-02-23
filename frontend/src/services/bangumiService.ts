import { request } from './client';

// 观看类型枚举
export enum WatchType {
  MEAL = 1,      // 饭点
  LEISURE = 2,   // 闲暇
  LONG_GRASS = 3, // 长草
  NEW = 4        // 新番
}

// 收藏信息接口
export interface CollectionInfo {
  id?: string;
  type?: number; // 收藏类型：1想看/2看过/3在看/4搁置/5抛弃
  rate?: number; // 用户评分 (0-10)
  comment?: string; // 用户评论
  private?: boolean; // 是否私有收藏
  tags?: string[]; // 用户自定义标签列表
  vol_status?: number; // 卷数状态
  ep_status?: number; // 集数状态
  subject_type?: number; // 条目类型
  source: string; // 数据来源：bangumi/douban
  source_id: string; // 原站ID（Bangumi ID或豆瓣ID）
  updated_at?: string; // 最后更新时间
  user_id: number; // 用户ID
}

// 条目信息接口
export interface SubjectInfo {
  id: number; // 数据库自增主键
  name: string; // 条目原名
  name_cn?: string; // 条目中文名
  type: number; // 条目类型：1=书籍/2=动画/3=音乐/4=游戏/6=三次元
  source: string; // 数据来源：bangumi/douban
  source_id: string; // 原站ID（Bangumi ID或豆瓣ID）
  summary?: string; // 条目简介
  date?: string; // 发售/放送日期
  platform?: string; // 平台/类型（如TV、小说、Switch等）
  eps?: number; // 集数（针对动画）
  volumes?: number; // 卷数（针对书籍）
  images?: Record<string, string>; // 图片字典（支持多尺寸图片）
  image?: string; // 单个封面图片URL
  tags?: Array<Record<string, any>>; // 标签列表
  meta_tags?: string[]; // 官方元标签
  infobox?: Array<Record<string, any>>; // 详细元数据（如作者、开发商等）
  rating?: Record<string, any>; // 评分信息
  collection?: Record<string, any>; // 收藏状态统计
  series?: boolean; // 是否为系列
  locked?: boolean; // 是否锁定
  nsfw?: boolean; // 是否不适合儿童
  air_time?: string | null; // 放送时间
  air_weekday?: number | null; // 放送星期 (1-7)
  last_sync?: string | null; // 最后同步时间
}

// 定义 Bangumi 日历数据类型
export interface BangumiItem {
  collection?: CollectionInfo | null; // 收藏信息
  subject: SubjectInfo; // 条目信息
  watch_day?: number; // 观看星期几
  watch_time?: string; // 观看时间
  duration?: number; // 观看周期
  watch_type?: WatchType; // 观看类型
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
        let watch_time = '';
        if (item.air_date) {
          // 尝试从 air_date 中提取时间
          const timeMatch = item.air_date.match(/\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2})/);
          if (timeMatch) {
            watch_time = timeMatch[1];
          }
        }
        
        // 创建前端需要的 BangumiItem
        items.push({
          collection: null,
          subject: {
            id: item.id,
            name: item.name,
            name_cn: item.name_cn || item.name,
            type: 2, // 默认动画类型
            source: 'bangumi',
            source_id: item.id.toString(),
            images: {
              common: '',
              large: '',
              medium: '',
              small: ''
            },
            air_weekday: item.air_weekday
          },
          watch_day: day_of_week,
          watch_time: watch_time,
          watch_type: WatchType.NEW,
          duration: 1
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
      let watch_time = '';
      // 默认先用后端给的 air_weekday 兜底 (如果是7转成0)
      let watch_day = subject.air_weekday ? (subject.air_weekday === 7 ? 0 : subject.air_weekday) : 0;

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
            watch_time = `${localHour}:${localMinute}`;
            
            // ✨ 核心修改：利用本地化后的 Date 对象直接获取星期几，覆盖后端的 weekday
            // utcDate.getDay() 返回的就是 0-6（0代表周日），完美契合你的设定
            watch_day = utcDate.getDay();
          }
        } catch (error) {
          console.error('时间解析失败:', subject.air_time, error);
        }
      }

      // 创建前端需要的 BangumiItem
      items.push({
        collection: item.collection || null,
        subject: {
          id: subject.id,
          name: subject.name,
          name_cn: subject.name_cn,
          type: subject.type,
          source: subject.source,
          source_id: subject.source_id,
          summary: subject.summary ?? undefined,
          date: subject.date,
          platform: subject.platform,
          eps: subject.eps ?? undefined,
          volumes: subject.volumes ?? undefined,
          images: subject.images,
          image: subject.image,
          tags: subject.tags,
          meta_tags: subject.meta_tags,
          infobox: subject.infobox,
          rating: subject.rating,
          collection: subject.collection,
          series: subject.series,
          locked: subject.locked,
          nsfw: subject.nsfw,
          air_time: subject.air_time,
          air_weekday: subject.air_weekday,
          last_sync: subject.last_sync
        },
        watch_day: watch_day,   // watch_day 也同步更新
        watch_type: WatchType.NEW,
        watch_time: watch_time,   // watch_time 也同步更新
        duration: 1
      });
    });
    
    return items;
  } catch (error) {
    console.error('同步 Bangumi 日历数据失败:', error);
    throw error;
  }
};
