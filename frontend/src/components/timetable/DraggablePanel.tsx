import React, { useState, useMemo } from 'react';
import { DraggablePanel, Flexbox, Segmented, ActionIcon, Icon } from '@lobehub/ui';
import { Typography, Badge, Dropdown, Tooltip } from 'antd';
import { Filter, LayoutGrid, Tv, Book, Gamepad2, Film } from 'lucide-react';
import TimelineMediaCard from './TimelineMediaCard';
import DraggableItemWrapper from './DraggableItemWrapper';
import { BangumiItem, WatchType } from '@/services/bangumiService';

const { Text } = Typography;

// --- 1. 模拟数据结构 ---
const MOCK_DATA: BangumiItem[] = [
  { 
    id: '1', 
    title: '葬送的芙莉莲', 
    source: 'local', 
    source_id: '1', 
    day_of_week: 0, 
    start_time: '18:00', 
    user_id: 1, 
    images: { 
      common: '...', 
      large: '...', 
      medium: '...', 
      small: '...' 
    },
    watch_type: WatchType.NEW
  },
  { 
    id: '2', 
    title: '迷宫饭', 
    source: 'local', 
    source_id: '2', 
    day_of_week: 1, 
    start_time: '18:30', 
    user_id: 1, 
    images: { 
      common: '...', 
      large: '...', 
      medium: '...', 
      small: '...' 
    },
    watch_type: WatchType.NEW
  },
  { 
    id: '3', 
    title: '沙丘', 
    source: 'local', 
    source_id: '3', 
    day_of_week: 2, 
    start_time: '20:00', 
    user_id: 1, 
    images: { 
      common: '...', 
      large: '...', 
      medium: '...', 
      small: '...' 
    },
    watch_type: WatchType.LEISURE
  },
  { 
    id: '4', 
    title: '百年孤独', 
    source: 'local', 
    source_id: '4', 
    day_of_week: 3, 
    start_time: '19:00', 
    user_id: 1, 
    images: { 
      common: '...', 
      large: '...', 
      medium: '...', 
      small: '...' 
    },
    watch_type: WatchType.LEISURE
  },
  { 
    id: '5', 
    title: '塞尔达传说：王国之泪', 
    source: 'local', 
    source_id: '5', 
    day_of_week: 4, 
    start_time: '21:00', 
    user_id: 1, 
    images: { 
      common: '...', 
      large: '...', 
      medium: '...', 
      small: '...' 
    },
    watch_type: WatchType.LONG_GRASS
  },
  { 
    id: '6', 
    title: '星空', 
    source: 'local', 
    source_id: '6', 
    day_of_week: 5, 
    start_time: '22:00', 
    user_id: 1, 
    images: { 
      common: '...', 
      large: '...', 
      medium: '...', 
      small: '...' 
    },
    watch_type: WatchType.LONG_GRASS
  },
];

// 分类映射
const CATEGORY_MAP = {
  all: '全部',
  anime: '动画',
  book: '书籍',
  game: '游戏',
  movie: '三次元',
};

const STATUS_MAP: Record<string, string> = {
  all: '全部状态',
  wish: '想看',
  watching: '在看',
  watched: '看过',
  on_hold: '搁置',
};

const STATUS_COLORS: Record<string, string> = {
  wish: 'blue',
  watching: 'green',
  watched: 'gray',
  on_hold: 'orange',
};

export const CollectionPanel = () => {
  const [expand, setExpand] = useState(true);
  
  // --- 2. 核心状态管理 ---
  const [activeType, setActiveType] = useState('all'); 
  const [activeStatus, setActiveStatus] = useState('all');

  // --- 3. 过滤逻辑 ---
  const filteredList = useMemo(() => {
    return MOCK_DATA.filter(item => {
      // 由于我们现在使用的是 BangumiItem 接口，需要根据 watch_type 来匹配类型
      let matchType = true;
      if (activeType !== 'all') {
        switch (activeType) {
          case 'anime':
            matchType = item.watch_type === WatchType.NEW;
            break;
          case 'book':
            matchType = item.watch_type === WatchType.LEISURE;
            break;
          case 'game':
            matchType = item.watch_type === WatchType.LONG_GRASS;
            break;
          case 'movie':
            matchType = item.watch_type === WatchType.LEISURE;
            break;
          default:
            matchType = true;
        }
      }
      // 暂时忽略状态过滤，因为我们的 BangumiItem 接口中没有 status 字段
      const matchStatus = true;
      return matchType && matchStatus;
    }).sort((a, b) => {
      // 按标题字母顺序排序
      return a.title.localeCompare(b.title);
    });
  }, [activeType, activeStatus]);



  return (
    <DraggablePanel
      expand={expand}
      mode="fixed"
      placement="right"
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: 350,
        // 增强毛玻璃质感
        backgroundColor: 'rgba(255, 255, 255, 0.65)',
        backdropFilter: 'blur(16px)',
        borderLeft: '1px solid rgba(255, 255, 255, 0.4)', // 微妙的边缘高光
        boxShadow: '-4px 0 24px rgba(0, 0, 0, 0.04)',
      }}
      onExpandChange={setExpand}
    >
      <Flexbox height="100%" width="100%" style={{ overflow: 'hidden' }}>
        
        {/* Header 区域：标题 */}
        <Flexbox padding="24px 20px 16px" align="center" justify="center">
          <Text style={{ fontSize: 18, fontWeight: 600, color: 'var(--ant-color-text)', textAlign: 'center' }}>
            我的收藏
          </Text>
        </Flexbox>

        {/* 筛选区域 */}
        <Flexbox padding="0 20px 16px" gap={16} align="center" justify="center">
          <Flexbox horizontal align="center" gap={16}>
            
        <Segmented
          value={activeType}
          onChange={(value) => setActiveType(value as string)}
          options={[
            {
              value: 'all',
              label: (
                <Tooltip title={CATEGORY_MAP.all}>
                  <div style={{ 
                    color: activeType === 'all' ? 'var(--ant-color-primary)' : 'var(--ant-color-text-tertiary)',
                    transition: 'color 0.3s'
                  }}>
                    <Icon icon={LayoutGrid} />
                  </div>
                </Tooltip>
              )
            },
            {
              value: 'anime',
              label: (
                <Tooltip title={CATEGORY_MAP.anime}>
                  <div style={{ 
                    color: activeType === 'anime' ? 'var(--ant-color-primary)' : 'var(--ant-color-text-tertiary)',
                    transition: 'color 0.3s'
                  }}>
                    <Icon icon={Tv} />
                  </div>
                </Tooltip>
              )
            },
            {
              value: 'book',
              label: (
                <Tooltip title={CATEGORY_MAP.book}>
                  <div style={{ 
                    color: activeType === 'book' ? 'var(--ant-color-primary)' : 'var(--ant-color-text-tertiary)',
                    transition: 'color 0.3s'
                  }}>
                    <Icon icon={Book} />
                  </div>
                </Tooltip>
              )
            },
            {
              value: 'game',
              label: (
                <Tooltip title={CATEGORY_MAP.game}>
                  <div style={{ 
                    color: activeType === 'game' ? 'var(--ant-color-primary)' : 'var(--ant-color-text-tertiary)',
                    transition: 'color 0.3s'
                  }}>
                    <Icon icon={Gamepad2} />
                  </div>
                </Tooltip>
              )
            },
            {
              value: 'movie',
              label: (
                <Tooltip title={CATEGORY_MAP.movie}>
                  <div style={{ 
                    color: activeType === 'movie' ? 'var(--ant-color-primary)' : 'var(--ant-color-text-tertiary)',
                    transition: 'color 0.3s'
                  }}>
                    <Icon icon={Film} />
                  </div>
                </Tooltip>
              )
            }
          ]}
          variant='borderless'
          shadow
          glass
        />
            
            {/* 使用 Dropdown 隐藏次要筛选条件 */}
            <Dropdown 
              menu={{ 
                items: Object.entries(STATUS_MAP).map(([key, label]) => ({
                  key,
                  label,
                  onClick: () => setActiveStatus(key)
                })),
                title: "状态筛选"
              }} 
              trigger={['click']}
            >
              <button 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '40px',
                  height: '40px',
                  borderRadius: '8px',
                  border: '1px solid var(--lobe-color-border)',
                  background: 'var(--lobe-color-bg-container)',
                  color: activeStatus !== 'all' ? 'var(--ant-color-primary)' : 'var(--lobe-color-text-primary)',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                title="状态筛选"
              >
                <Filter size={18} />
              </button>
            </Dropdown>
          </Flexbox>
        </Flexbox>

        {/* 列表区 */}
        <Flexbox flex={1} padding="0 16px 20px" gap={8} style={{ overflowY: 'auto' }}>
          {filteredList.length > 0 ? (
            filteredList.map(item => (
              <Flexbox 
                key={item.id} 
                style={{ 
                  cursor: 'pointer',
                  padding: '12px',
                  borderRadius: 16,
                  backgroundColor: 'transparent',
                  transition: 'all 0.25s cubic-bezier(0.2, 0, 0, 1)',
                  height: '104px', // 固定高度，包含 padding
                }}
                // hover 时增加轻微的背景和上浮效果
                className="hover:bg-white/80 hover:shadow-sm hover:-translate-y-0.5"
              >
                <DraggableItemWrapper id={item.id}>
                  <TimelineMediaCard 
                    data={item} 
                    currentHeight={80} // 使用正常高度卡片，适合显示方形封面
                  />
                </DraggableItemWrapper>
              </Flexbox>
            ))
          ) : (
            <Flexbox align="center" justify="center" flex={1} style={{ color: 'var(--ant-color-text-tertiary)' }}>
              暂无数据
            </Flexbox>
          )}
        </Flexbox>
      </Flexbox>
    </DraggablePanel>
  );
};

export default CollectionPanel;