import { ActionIcon, SearchBar as LobeSearchBar } from '@lobehub/ui';
import { Popover, Input, Button, Tag, Space } from 'antd';
import { Hash, FileCode, Search, Star, CheckCircle2 } from 'lucide-react';
import React, { useState, useRef } from 'react';
import { searchService, SearchResult } from '../../services/search';

// 搜索面板的样式容器
const SearchPanelWrapper = ({ children }: { children: React.ReactNode }) => (
  <div style={{ width: 320, padding: 4 }}>
    {children}
  </div>
);

// 搜索结果数据结构
export interface SearchResultItem {
  id: string;
  title: string;
  cover: string;
  score: number;
  tags: string[];
  hasCollection: boolean;
  source: string;
  sourceId: number;
  fullItem?: any; // 存储完整的 item 结构
}

// 修改 Props 定义，增加 onSelect 回调
interface SearchTriggerProps {
  onSelect?: (item: SearchResultItem) => void; // 新增
}

// 在组件参数里解构 onSelect
const SearchTrigger = ({ onSelect }: SearchTriggerProps) => {
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 处理搜索
  const handleSearch = async (isLoadMore = false) => {
    if (!keyword && !isLoadMore) return;
    if (isLoadMore) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      setOffset(0); // 重置偏移量
    }

    try {
      // 获取当前偏移量
      const currentOffset = isLoadMore ? offset : 0;
      
      // 调用搜索服务
      const searchResults = await searchService.searchSubjects({
        keyword,
        offset: currentOffset,
        limit: 10
      });
      
      // 处理搜索结果
      if (searchResults && searchResults.length > 0) {
        const results = searchResults.map((item: SearchResult): SearchResultItem => {
          const subject = item.subject;
          const collection = item.collection;
          
          return {
            id: `${subject.source}-${subject.source_id}`,
            title: subject.name_cn || subject.name || keyword,
            cover: subject.image || (subject.images && subject.images.common ? subject.images.common : ''),
            score: subject.rating && subject.rating.score ? subject.rating.score : (subject.score || 0),
            tags: subject.tags ? subject.tags.map((tag: any) => tag.name || tag) : [],
            hasCollection: !!collection,
            source: subject.source,
            sourceId: subject.source_id ?? 0,
            fullItem: item // 存储完整的 item 结构
          };
        });

        if (isLoadMore) {
          // 加载更多
          setSearchResults(prev => [...prev, ...results]);
          setOffset(prev => prev + 10);
          setHasMore(results.length >= 10);
        } else {
          setSearchResults(results);
          setOffset(10);
          setHasMore(results.length >= 10);
        }
      } else {
        if (!isLoadMore) {
          setSearchResults([]);
        }
        setHasMore(false);
      }
    } catch (error) {
      console.error('Search error:', error);
    } finally {
      if (isLoadMore) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  };

  // 加载更多结果
  const loadMoreResults = () => {
    if (!loadingMore && hasMore) {
      handleSearch(true);
    }
  };

  // 处理滚动事件
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    const scrollTop = target.scrollTop;
    const scrollHeight = target.scrollHeight;
    const clientHeight = target.clientHeight;
    
    // 当滚动到距离底部 50px 时加载更多
    if (scrollHeight - scrollTop - clientHeight < 50) {
      loadMoreResults();
    }
  };

  // 处理结果选择
  const handleResultSelect = (item: SearchResultItem) => {
    if (onSelect) {
      onSelect(item);
      setOpen(false); // 选中后关闭浮层
    }
    setKeyword(''); // 清空搜索
  };

  // 弹出层的内容（搜索框 + 列表）
  const content = (
    <SearchPanelWrapper>
      {/* 搜索框 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <Input 
          placeholder="搜索动漫名称" 
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => handleSearch(false)}
          style={{ flex: 1 }}
        />
        <Button type="primary" onClick={() => handleSearch(false)} loading={loading}>
          搜索
        </Button>
      </div>
      
      {/* 搜索结果列表 */}
      <div
        ref={dropdownRef}
        onScroll={handleScroll}
        style={{
          maxHeight: 300,
          overflowY: 'auto',
          borderRadius: 8,
          border: '1px solid #e5e7eb',
          backgroundColor: '#ffffff'
        }}
      >
        {searchResults.length > 0 ? (
          searchResults.map((item) => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                gap: 8,
                padding: 8,
                borderRadius: 6,
                margin: 4,
                backgroundColor: '#ffffff',
                border: '1px solid #e5e7eb',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onClick={() => handleResultSelect(item)}
              className="search-item"
            >
              {/* 封面图 */}
              <img
                src={item.cover}
                alt={item.title}
                style={{
                  width: 40,
                  height: 56,
                  objectFit: 'cover',
                  borderRadius: 4
                }}
              />
              
              {/* 内容区域 */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <h4 style={{ margin: 0, fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.title}
                  </h4>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <Star size={12} color="#ffd700" />
                      <span style={{ fontSize: 12, color: '#666' }}>{item.score}</span>
                    </div>
                    {item.hasCollection && (
                      <CheckCircle2 size={12} color="#52c41a" />
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {item.tags.slice(0, 3).map((tag, index) => (
                    <Tag key={index} style={{ fontSize: 10, padding: '0 6px', height: 18 }}>
                      {tag}
                    </Tag>
                  ))}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div style={{ padding: 16, textAlign: 'center', color: '#999', fontSize: 12 }}>
            {keyword ? '未找到相关结果' : '请输入搜索关键词'}
          </div>
        )}
        
        {/* 加载更多提示 */}
        {loadingMore && (
          <div style={{ padding: 8, textAlign: 'center', fontSize: 12, color: '#999' }}>
            加载中...
          </div>
        )}
        
        {!hasMore && searchResults.length > 0 && (
          <div style={{ padding: 8, textAlign: 'center', fontSize: 12, color: '#999' }}>
            没有更多结果了
          </div>
        )}
      </div>
    </SearchPanelWrapper>
  );

  return (
    <>
      <Popover
        content={content}
        trigger="click"
        open={open}
        onOpenChange={setOpen}
        placement="bottomLeft"
        // 抵消 Popover 的默认内边距，让我们的内容铺满
        styles={{ container: { padding: 4 } }}
      >
        <ActionIcon 
          icon={Search} 
          title="搜索并插入" 
          size={{ blockSize: 32 }}
          active={open} // 激活状态下图标会变色
        />
      </Popover>
      
      {/* 简单的 Hover 样式全局注入 */}
      <style>{`
        .search-item:hover {
          background: var(--lobe-color-fill-tertiary);
          border-color: var(--lobe-color-primary);
        }
      `}</style>
    </>
  );
};

export default SearchTrigger;