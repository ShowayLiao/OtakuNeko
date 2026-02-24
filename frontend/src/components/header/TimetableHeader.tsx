"use client";

import {Header} from './Header';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { SearchBar, Button, Popover, Flexbox, Tag, Alert, toast } from '@lobehub/ui';
import { Calendar, CloudSync, ChevronDown, CloudDownload, HardDriveDownload, Share, Save, CalendarArrowUp, ListTodo } from 'lucide-react';
import { useState } from 'react';
import { bulkUpsertSchedules, ScheduleBase, convertBangumiItemsToSchedules, getSchedules } from '@/services/scheduleService';

interface TimetableHeaderProps {
  onSearch?: (value: string) => void;
  onViewModeChange?: (mode: 'grid' | 'list') => void;
  schedules?: any[];
  onSaveSuccess?: () => void;
  onSyncData?: (data: any[]) => void;
}

export default function TimetableHeader({ 
  onSearch, 
  onViewModeChange,
  schedules = [],
  onSaveSuccess,
  onSyncData
}: TimetableHeaderProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const handleSaveSchedules = async () => {
    if (schedules.length === 0) {
      toast.warning('没有可保存的日程');
      return;
    }

    setIsSaving(true);

    try {
      // 在传输给后端前进行数据转换
      const convertedSchedules = convertBangumiItemsToSchedules(schedules);
      
      if (convertedSchedules.length === 0) {
        toast.warning('没有有效的日程数据');
        return;
      }
      
      await bulkUpsertSchedules(convertedSchedules);
      onSaveSuccess?.();
      // 显示成功提示
      toast.success('保存成功');
    } catch (error) {
      console.error('保存日程失败:', error);
      toast.error('保存失败，请重试');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSyncData = async () => {
    setIsSyncing(true);

    try {
      // 调用 getSchedules API 获取数据
      const syncData = await getSchedules();
      
      // 调用回调函数，将数据传递给父组件
      onSyncData?.(syncData);
      
      // 显示成功提示
      toast.success('同步数据成功');
    } catch (error) {
      console.error('同步数据失败:', error);
      toast.error('同步失败，请重试');
    } finally {
      setIsSyncing(false);
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
                    onClick={handleSyncData}
                  >
                    <HardDriveDownload size={16} style={{ marginRight: 10 }} />
                    <span style={{ flex: 1, fontSize: 14 }}>{isSyncing ? '同步中...' : '同步云端'}</span>
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