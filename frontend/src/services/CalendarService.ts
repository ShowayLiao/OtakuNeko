import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import { BangumiItem, WatchType } from './bangumiService';
dayjs.extend(isoWeek); // 启用 isoWeek，确保周一为每周第一天 (1=周一, 7=周日)

export function generateCalendarEvents(items: BangumiItem[]) {
  const events: any[] = [];
  const now = dayjs();

  // 遍历所有项目
  items.forEach(item => {
    const subjectName = item.subject?.name_cn || item.subject?.name || '未知动画';

    // 获取本周一的基准日期（去除时间部分）
    const startOfThisWeek = now.startOf('isoWeek'); 
    
    // 计算本周你计划观看的具体日期：本周一 + 设定星期几
    // 假设 item.watch_day 是 0-6 (0为周一，1为周二，...，6为周日)
    const watchDayOffset = item.watch_day || 0;
    const baseWatchDate = startOfThisWeek.add(watchDayOffset, 'day');

    if (item.watch_type === WatchType.NEW) {
      // 【新番逻辑】
      if (!item.subject?.air_time) return;
      
      const airDate = dayjs(item.subject.air_time);
      const totalEps = item.subject.eps || 12; // 没数据默认季番12集
      const watchTime = item.watch_time || '20:00'; // 默认晚上8点看
      
      // 计算播出进度
      const weeksPassed = Math.floor(now.diff(airDate, 'day') / 7);
      const remainingEps = Math.max(0, totalEps - weeksPassed);
      
      // 如果这周的观看时间已经过了，你可以决定是从这周算还是下周算
      // 这里默认基于本周的 watch_day 往后推算
      for (let i = 0; i < remainingEps; i++) {
        const eventDate = baseWatchDate.add(i, 'week').format('YYYY-MM-DD');
        events.push({
          Subject: `[新番] ${subjectName} (余${remainingEps - i}次)`,
          StartDate: eventDate,
          StartTime: watchTime,
          AllDay: false
        });
      }

    } else {
      // 【非新番逻辑】
      const durationDays = item.duration || 1;
      // 结束日期：起始日 + duration (直接加，符合日历全天事件排他性标准)
      const endDate = baseWatchDate.add(durationDays, 'day');

      if (item.watch_type === WatchType.MEAL) {
        // 饭点动画：在 duration 周期内，每天 12点和 18点生成
        for (let i = 0; i < durationDays; i++) {
          const currentDate = baseWatchDate.add(i, 'day').format('YYYY-MM-DD');
          events.push(
            { Subject: `[午饭] ${subjectName}`, StartDate: currentDate, StartTime: '12:00', AllDay: false },
            { Subject: `[晚饭] ${subjectName}`, StartDate: currentDate, StartTime: '18:00', AllDay: false }
          );
        }
      } else {
        // 闲暇/长草动画：生成跨越 duration 的全天事件
        events.push({
          Subject: `[${item.watch_type === WatchType.LEISURE ? '闲暇' : '长草'}] ${subjectName}`,
          StartDate: baseWatchDate.format('YYYY-MM-DD'),
          EndDate: endDate.format('YYYY-MM-DD'),
          AllDay: true
        });
      }
    }
  });

  return events;
}

// 假设传入的是上一段代码生成的 events 数组
export function generateCSVString(events: any[]): string {
  // 1. 定义标准日历 CSV 表头
  const headers = [
    'Subject',      // 标题
    'Start Date',   // 开始日期 (YYYY-MM-DD)
    'Start Time',   // 开始时间 (HH:mm)
    'End Date',     // 结束日期 (YYYY-MM-DD)
    'End Time',     // 结束时间 (HH:mm)
    'All Day Event',// 是否全天 (True/False)
    'Description'   // 备注说明
  ];

  // 2. 遍历数据生成 CSV 行
  const rows = events.map(event => {
    // 处理标题中的逗号或双引号（CSV格式要求包含逗号的字符串必须用双引号包裹）
    const safeSubject = `"${event.Subject.replace(/"/g, '""')}"`;
    const startDate = event.StartDate;
    const allDay = event.AllDay ? 'True' : 'False';
    
    let endDate = event.EndDate || event.StartDate; // 没有传 EndDate 就默认和 StartDate 同一天
    let startTime = event.StartTime || '';
    let endTime = '';

    // 如果不是全天事件，默认加上 30 分钟的结束时间
    if (!event.AllDay && event.StartTime) {
      endTime = dayjs(`${startDate} ${startTime}`).add(30, 'minute').format('HH:mm');
    }

    return [
      safeSubject, 
      startDate, 
      startTime, 
      endDate, 
      endTime, 
      allDay, 
      '""' // Description 留空，你可以根据需要填入 item.subject.summary
    ].join(',');
  });

  // 3. 拼接表头和数据，使用 \n 换行
  return [headers.join(','), ...rows].join('\n');
}

// 星期映射表，用于把 1-7 转成中文
const WEEKDAY_MAP = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

export function generateVoiceCommand(item: BangumiItem): string {
  const subjectName = item.subject?.name_cn || item.subject?.name || '未知动画';
  const watchDay = WEEKDAY_MAP[item.watch_day || 0]; // 例如："周三"
  
  switch (item.watch_type) {
    case WatchType.NEW:
      // 新番：利用语音助手的“每周重复”功能
      const time = item.watch_time || '晚上8点';
      let remainingEps = 0;
      if (item.subject?.air_time) {
        const totalEps = item.subject.eps || 12;
        const airDate = dayjs(item.subject.air_time);
        const weeksPassed = Math.floor(dayjs().diff(airDate, 'day') / 7);
        remainingEps = Math.max(0, totalEps - Math.max(0, weeksPassed));
      }
      return `帮我设置一个日历日程，从本${watchDay}的${time}开始，标题为“看新番《${subjectName}》”，并且设置为每周重复，共重复 ${remainingEps} 次。`;

    case WatchType.MEAL:
      // 饭点：利用语音助手的“连续多天”功能
      const duration = item.duration || 1;
      return `帮我设置日历，从本${watchDay}开始，连续 ${duration} 天，每天的中午12点和下午6点各添加一个日程，标题叫“吃饭看《${subjectName}》”。`;

    case WatchType.LEISURE:
    case WatchType.LONG_GRASS:
      // 闲暇/长草：利用语音助手的“多天全天日程”功能
      const endDayOffset = (item.watch_day || 1) - 1 + (item.duration || 1) - 1; 
      // 简单粗暴的兜底话术，避免跨周计算太复杂导致语音助手听不懂
      return `帮我添加一个全天日程，从本${watchDay}开始，持续 ${item.duration || 1} 天，标题为“补番《${subjectName}》”。`;

    default:
      return `提醒我抽空看《${subjectName}》。`;
  }
}

// ⬇️ ---------- 这里是为你新增的滴答清单专用服务 ---------- ⬇️

export interface TickTickOptions {
  listName?: string;
  priority?: string;
  tags?: string[];
}


export function generateAllTickTickCommands(items: BangumiItem[], options: TickTickOptions): string {
  if (!items || items.length === 0) return '当前课表中没有番剧数据';

  // 遍历所有番剧，调用单体生成函数，并用两个换行符连接
  return items
    .map((item) => {
      const command = generateTickTickCommand(item, options);
      return command;
    })
    .join('\n\n'); // 不同番剧之间空一行，方便滴答清单识别和视觉区分
}

export function generateTickTickCommand(item: BangumiItem, options: TickTickOptions): string {
  const subjectName = item.subject?.name_cn || item.subject?.name || '未知动画';
  
  // 1. 动态拼接滴答清单的属性后缀 (例如：~追番 !高 #动画 #新番)
  const suffixParts: string[] = [];
  if (options.listName) suffixParts.push(`~${options.listName}`);
  if (options.priority && options.priority !== '无') suffixParts.push(`!${options.priority}`);
  if (options.tags && options.tags.length > 0) {
    suffixParts.push(options.tags.map(tag => `#${tag}`).join(' '));
  }
  const suffix = suffixParts.length > 0 ? ` ${suffixParts.join(' ')}` : '';

  const now = dayjs();
  const commands: string[] = [];

  switch (item.watch_type) {
    case WatchType.NEW: {
      const time = item.watch_time || '20:00';
      let remainingEps = 12;
      let currentEp = 1; // 记录从第几集开始看
      
      if (item.subject?.air_time) {
        const totalEps = item.subject.eps || 12;
        const airDate = dayjs(item.subject.air_time);
        const weeksPassed = Math.floor(now.diff(airDate, 'day') / 7);
        // 确保不会出现负数集数
        remainingEps = Math.max(1, totalEps - Math.max(0, weeksPassed));
        currentEp = Math.max(1, weeksPassed + 1); 
      }

      // 计算基准日期（本周你要看的那天）
      const startOfThisWeek = now.startOf('isoWeek'); 
      const watchDayOffset = item.watch_day || 0;
      let baseWatchDate = startOfThisWeek.add(watchDayOffset, 'day');
      
      // 如果本周该追番时间已经过了，直接从下周算起
      if (baseWatchDate.isBefore(now, 'day')) {
        baseWatchDate = baseWatchDate.add(1, 'week');
      }

      // 核心：循环展开，生成多行带具体日期的独立任务
      for (let i = 0; i < remainingEps; i++) {
        // 格式化输出: YYYY/MM/DD HH:mm
        const epDate = baseWatchDate.add(i, 'week').format('YYYY/MM/DD');
        commands.push(`${epDate} ${time}  ${subjectName} 第${currentEp + i}集${suffix}`);
      }
      return commands.join('\n');
    }

    case WatchType.MEAL: {
      const duration = item.duration || 1;
      for (let i = 0; i < duration; i++) {
        const epDate = now.add(i, 'day').format('YYYY/MM/DD');
        commands.push(`${epDate} 12:00 ${subjectName} ${suffix}`);
        commands.push(`${epDate} 18:00 ${subjectName} ${suffix}`);
      }
      return commands.join('\n');
    }

    case WatchType.LEISURE: {
      const duration = item.duration || 1;
      for (let i = 0; i < duration; i++) {
        const epDate = now.add(i, 'day').format('YYYY/MM/DD');
        commands.push(`${epDate} 阅读 ${subjectName} ${suffix}`);
      }
      return commands.join('\n');
    }

    case WatchType.LONG_GRASS: {
      const duration = item.duration || 1;
      for (let i = 0; i < duration; i++) {
        const epDate = now.add(i, 'day').format('YYYY/MM/DD');
        commands.push(`${epDate} 补番 ${subjectName} ${suffix}`);
      }
      return commands.join('\n');
    }

    default:
      return `看《${subjectName}》${suffix}`;
  }
}



// ⬆️ -------------------------------------------------------- ⬆️

export const downloadCSV = (csvContent: string, filename: string) => {
  // 添加 BOM 头，防止 Excel 打开时中文乱码
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `${filename}.csv`);
  link.style.visibility = 'hidden';
  
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};