import { describe, expect, it } from 'vitest';

import {
  generateCalendarEvents,
  generateCSVString,
  generateVoiceCommand,
} from './CalendarService';
import { WatchType } from './bangumiService';

const subject = {
  id: 1,
  name: 'Example Anime',
  name_cn: '示例动画',
  type: 2,
  source: 'bangumi',
  source_id: '1',
};

describe('CalendarService local pure functions', () => {
  it('generates two events per day for a two-day meal plan', () => {
    const events = generateCalendarEvents([
      { subject, watch_type: WatchType.MEAL, watch_day: 0, duration: 2 },
    ]);

    expect(events).toHaveLength(4);
    expect(events.every(event => event.Subject === '[午饭] 示例动画' || event.Subject === '[晚饭] 示例动画')).toBe(true);
  });

  it('escapes CSV quotes and defaults an event end date', () => {
    const csv = generateCSVString([
      {
        Subject: '示例, "特别"',
        StartDate: '2026-07-31',
        StartTime: '20:00',
        AllDay: false,
      },
    ]);

    expect(csv).toContain('"示例, ""特别""",2026-07-31,20:00,2026-07-31,20:30,False,""');
  });

  it('generates a local voice command without a network request', () => {
    const command = generateVoiceCommand({
      subject,
      watch_type: WatchType.MEAL,
      watch_day: 0,
      duration: 2,
    });

    expect(command).toContain('连续 2 天');
    expect(command).toContain('吃饭看《示例动画》');
  });
});
