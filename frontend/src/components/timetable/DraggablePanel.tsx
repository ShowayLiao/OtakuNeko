import React, { useState, useMemo, useEffect } from 'react';
import { DraggablePanel, Flexbox, Segmented, ActionIcon, Icon } from '@lobehub/ui';
import { Typography, Badge, Dropdown, Tooltip, Spin } from 'antd';
import { Filter, LayoutGrid, Tv, Book, Gamepad2, Film } from 'lucide-react';
import TimelineMediaCard from './TimelineMediaCard';
import DraggableItemWrapper from './DraggableItemWrapper';
import { BangumiItem } from '@/services/bangumiService';
import { getCollections } from '@/services/scheduleService';

const { Text } = Typography;

// 分类映射
const CATEGORY_MAP = {
  all: '全部',
  anime: '动画',
  book: '书籍',
  game: '游戏',
  movie: '三次元',
};

// 分类到后端参数的映射
const CATEGORY_TO_TYPE_MAP = {
  anime: 2, // 动画
  book: 1, // 书籍
  game: 4, // 游戏
  movie: 6, // 三次元
};

const STATUS_MAP: Record<string, string> = {
  all: '全部状态',
  wish: '想看',
  watching: '在看',
  watched: '看过',
  on_hold: '搁置',
};

// 状态到后端参数的映射
const STATUS_TO_STATUS_MAP = {
  wish: 1, // 想看
  watching: 3, // 在看
  watched: 2, // 看过
  on_hold: 4, // 搁置
};

const STATUS_COLORS: Record<string, string> = {
  wish: 'blue',
  watching: 'green',
  watched: 'gray',
  on_hold: 'orange',
};

interface CollectionPanelProps {
  searchQuery?: string;
}

export const CollectionPanel = ({ searchQuery = '' }: CollectionPanelProps) => {
  const [expand, setExpand] = useState(true);
  
  // --- 2. 核心状态管理 ---
  const [activeType, setActiveType] = useState('all'); 
  const [activeStatus, setActiveStatus] = useState('all');
  const [collections, setCollections] = useState<BangumiItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- 3. 数据获取逻辑 ---
  
  useEffect(() => {
    const fetchCollections = async () => {
      setLoading(true);
      setError(null);
      try {
        // 构建请求参数
        const params: any = {};
        if (activeType !== 'all') {
          params.subject_type = CATEGORY_TO_TYPE_MAP[activeType as keyof typeof CATEGORY_TO_TYPE_MAP];
        }
        if (activeStatus !== 'all') {
          params.status = STATUS_TO_STATUS_MAP[activeStatus as keyof typeof STATUS_TO_STATUS_MAP];
        }
        if (searchQuery) {
          params.keyword = searchQuery;
        }
        
        console.log('DraggablePanel: 发送请求参数:', params);
        
        const items = await getCollections(params);
        console.log('DraggablePanel: 收到响应数据:', items.length, '条');
        setCollections(items || []);
      } catch (err) {
        setError('获取收藏数据失败');
        console.error('Error fetching collections:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchCollections();
  }, [activeType, activeStatus, searchQuery]);

  // --- 4. 数据过滤和排序逻辑 ---
  const filteredList = useMemo(() => {
    // 直接使用后端返回的数据顺序，不进行前端排序
    return collections;
  }, [collections]);



  return (
    <DraggablePanel
      expand={expand}
      mode="fixed"
      placement="right"
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: 350,
        // 增强毛玻璃质感，使用 CSS 变量适配暗黑模式
        backgroundColor: 'var(--lobe-color-bg-container)',
        backdropFilter: 'blur(16px)',
        borderLeft: '1px solid var(--lobe-color-border)',
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
                    color: activeType === 'all' ? 'var(--ant-color-primary)' : 'var(--lobe-color-text-tertiary)',
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
                    color: activeType === 'anime' ? 'var(--ant-color-primary)' : 'var(--lobe-color-text-tertiary)',
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
                    color: activeType === 'book' ? 'var(--ant-color-primary)' : 'var(--lobe-color-text-tertiary)',
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
                    color: activeType === 'game' ? 'var(--ant-color-primary)' : 'var(--lobe-color-text-tertiary)',
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
                    color: activeType === 'movie' ? 'var(--ant-color-primary)' : 'var(--lobe-color-text-tertiary)',
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
          {loading ? (
            // 加载状态
            <Flexbox align="center" justify="center" flex={1}>
              <Spin size="default" tip="加载中..." />
            </Flexbox>
          ) : error ? (
            // 错误状态
            <Flexbox align="center" justify="center" flex={1} style={{ color: 'var(--ant-color-danger)' }}>
              {error}
            </Flexbox>
          ) : filteredList.length > 0 ? (
            // 有数据状态
            filteredList.map(item => (
              <Flexbox 
                key={`${item.subject.source}-${item.subject.source_id}`} 
                style={{ 
                  cursor: 'pointer',
                  padding: '12px',
                  borderRadius: 16,
                  backgroundColor: 'transparent',
                  transition: 'all 0.25s cubic-bezier(0.2, 0, 0, 1)',
                  height: '104px', // 固定高度，包含 padding
                }}
                // hover 时增加轻微的背景和上浮效果
                className="hover:shadow-sm hover:-translate-y-0.5"
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--lobe-color-bg-overlay)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <DraggableItemWrapper id={`panel-${item.subject.source}-${item.subject.source_id}`} data={item}>
                  <TimelineMediaCard 
                    data={item} 
                    currentHeight={80} // 使用正常高度卡片，适合显示方形封面
                    transparent={true} // 开启透明模式
                    isPanel={true} // 标识在 DraggablePanel 中渲染
                  />
                </DraggableItemWrapper>
              </Flexbox>
            ))
          ) : (
            // 空数据状态
            <Flexbox align="center" justify="center" flex={1} style={{ color: 'var(--lobe-color-text-tertiary)' }}>
              暂无收藏数据
            </Flexbox>
          )}
        </Flexbox>
      </Flexbox>
    </DraggablePanel>
  );
};

export default CollectionPanel;