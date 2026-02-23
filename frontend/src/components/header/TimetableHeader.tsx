"use client";

import {Header} from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { SearchBar, Button, Popover, Flexbox, Tag, Alert } from '@lobehub/ui';
import { Calendar, CloudSync, ChevronDown, CloudDownload, HardDriveDownload, Share, Save, CalendarArrowUp, ListTodo } from 'lucide-react';
import { useState } from 'react';
import { bulkUpsertSchedules, ScheduleBase } from '@/services/scheduleService';

interface TimetableHeaderProps {
  onSearch?: (value: string) => void;
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  schedules?: ScheduleBase[];
  onSaveSuccess?: () => void;
}

export default function TimetableHeader({ 
  onSearch, 
  onViewModeChange,
  schedules = [],
  onSaveSuccess
}: TimetableHeaderProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSaveSchedules = async () => {
    if (schedules.length === 0) {
      setSaveError('没有可保存的日程');
      setTimeout(() => setSaveError(null), 3000);
      return;
    }

    setIsSaving(true);
    setSaveError(null);

    try {
      await bulkUpsertSchedules(schedules);
      onSaveSuccess?.();
      // 显示成功提示
      setSaveError('保存成功');
      setTimeout(() => setSaveError(null), 3000);
    } catch (error) {
      console.error('保存日程失败:', error);
      setSaveError('保存失败，请重试');
      setTimeout(() => setSaveError(null), 3000);
    } finally {
      setIsSaving(false);
    }
  };
  const { primaryColor } = useAppTheme();
  // 搜索框通常保留本地状态，用于处理输入时的即时显示，回车或防抖后再通知父组件
  const [searchKw, setSearchKw] = useState('');

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchKw(value);
    onSearch?.(value);
  };

  return (
    <div className="w-full">
      <Header
        leftArea={
          <div className="flex items-center gap-3">
            <Calendar size={20} style={{ color: primaryColor }} />
            <span className="text-xl font-bold font-sans tracking-tight" style={{ color: primaryColor }}>
              动画时间表
            </span>
          </div>
        }
        centerArea={
          <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '16px' }}>
            {/* 数据同步菜单 */}
            <Popover
              arrow={false}
              placement="bottomLeft"
              trigger="hover"
              content={
                <Flexbox gap={6} style={{ minWidth: 160, padding: '8px' }}>
                  <div
                    style={{
                      color: 'var(--lobe-color-text-3)',
                      fontSize: 11,
                      fontWeight: 600,
                      letterSpacing: '0.5px',
                      padding: '4px 8px',
                      textTransform: 'uppercase',
                    }}
                  >
                    Data Sync
                  </div>
                  <Flexbox
                    horizontal
                    align="center"
                    style={{
                      borderRadius: 8,
                      cursor: 'pointer',
                      padding: '8px 12px',
                      transition: 'all 0.2s',
                    }}
                    className="hover:bg-gray-100 dark:hover:bg-gray-800"
                    onClick={handleSaveSchedules}
                  >
                    <CloudDownload size={16} style={{ marginRight: 10 }} />
                    <span style={{ flex: 1, fontSize: 14 }}>{isSaving ? '保存中...' : '保存日程'}</span>
                  </Flexbox>
                  <Flexbox
                    horizontal
                    align="center"
                    style={{
                      borderRadius: 8,
                      cursor: 'pointer',
                      padding: '8px 12px',
                      transition: 'all 0.2s',
                    }}
                    className="hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    <HardDriveDownload size={16} style={{ marginRight: 10 }} />
                    <span style={{ flex: 1, fontSize: 14 }}>同步云端</span>
                  </Flexbox>
                </Flexbox>
              }
            >
              <Button icon={<CloudSync size={16} />} style={{ gap: 6 }} type="text">
                同步数据
                <ChevronDown size={14} style={{ opacity: 0.6 }} />
              </Button>
            </Popover>

            {/* 导出分享菜单 */}
            <Popover
              arrow={false}
              placement="bottomLeft"
              trigger="hover"
              content={
                <Flexbox gap={6} style={{ minWidth: 160, padding: '8px' }}>
                  <div
                    style={{
                      color: 'var(--lobe-color-text-3)',
                      fontSize: 11,
                      fontWeight: 600,
                      letterSpacing: '0.5px',
                      padding: '4px 8px',
                      textTransform: 'uppercase',
                    }}
                  >
                    Export
                  </div>
                  <Flexbox
                    horizontal
                    align="center"
                    style={{
                      borderRadius: 8,
                      cursor: 'pointer',
                      padding: '8px 12px',
                      transition: 'all 0.2s',
                    }}
                    className="hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    <CalendarArrowUp size={16} style={{ marginRight: 10 }} />
                    <span style={{ flex: 1, fontSize: 14 }}>导出为日历 (ICS)</span>
                  </Flexbox>
                  <Flexbox
                    horizontal
                    align="center"
                    style={{
                      borderRadius: 8,
                      cursor: 'pointer',
                      padding: '8px 12px',
                      transition: 'all 0.2s',
                    }}
                    className="hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    <ListTodo size={16} style={{ marginRight: 10 }} />
                    <span style={{ flex: 1, fontSize: 14 }}>导出至滴答清单</span>
                  </Flexbox>
                </Flexbox>
              }
            >
              <Button icon={<Share size={16} />} style={{ gap: 6 }} type="text">
                导出数据
                <ChevronDown size={14} style={{ opacity: 0.6 }} />
              </Button>
            </Popover>

            <div style={{ marginLeft: 'auto' }}>
              <SearchBar 
                placeholder="搜索时间表..." 
                enableShortKey 
                shortKey="k"
                value={searchKw}
                onChange={handleSearchChange}
                // 建议加上 allowClear 方便用户一键清除
                allowClear 
                style={{ width: 240 }}
              />
            </div>
          </div>
        }
      />
    </div>
  );
}