import React, { useState, useRef } from 'react';
import { Modal, Button, Input, Icon, Tooltip, toast, Tag } from '@lobehub/ui';
import { Search, FileJson, BookOpen, XCircle, CheckCircle2, Star } from 'lucide-react';
import { searchService, SearchResult } from '../../services/search';
import { collectionService } from '../../services/collections';
import { useAppTheme } from '@/components/providers/LobeProvider';
import SubjectForm from './form/SubjectForm';
import { FormData } from './types';

// 添加加载动画样式
const style = document.createElement('style');
style.textContent = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;
document.head.appendChild(style);



interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ImportModal = ({ isOpen, onClose }: ImportModalProps) => {
  // --- 状态管理 ---
  const { isDarkMode } = useAppTheme();
  
  // 搜索模式状态
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  
  // 核心表单数据状态
  const [formData, setFormData] = useState<FormData>({
    title: '',
    subject: {
      id: 0,
      date: '',
      images: {
        small: '',
        grid: '',
        large: '',
        medium: '',
        common: ''
      },
      name: '',
      name_cn: '',
      short_summary: '',
      tags: [],
      score: 0,
      type: 0,
      eps: 0,
      volumes: 0,
      source: ''
    },
    cover: '',
    collectionType: 0,
    rate: 0,
    comment: '',
    volStatus: 0,
    epStatus: 0,
    tags: ''
  });
  
  // JSON 错误状态
  const [jsonError, setJsonError] = useState('');
  
  // 搜索结果状态
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  
  // 控制搜索结果下拉框显示
  const [showDropdown, setShowDropdown] = useState<boolean>(false);
  
  // 分页相关状态
  const [offset, setOffset] = useState<number>(0);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // --- 逻辑处理 ---

  // A. 搜索并自动填入逻辑
  const handleSearch = async (isLoadMore = false) => {
    if (!keyword && !isLoadMore) return;
    if (isLoadMore) {
      setLoadingMore(true);
    } else {
      setLoading(true);
      // 重置分页状态
      setOffset(0);
      setHasMore(true);
    }

    try {
      // 调用搜索服务进行搜索
      const currentOffset = isLoadMore ? offset : 0;
      const results = await searchService.searchSubjects({
        keyword,
        offset: currentOffset,
        limit: 10
      });
      
      // 处理搜索结果
      if (results && results.length > 0) {
        // 存储完整搜索结果并显示下拉框
        if (isLoadMore) {
          setSearchResults(prev => [...prev, ...results]);
          setOffset(prev => prev + 10);
        } else {
          setSearchResults(results);
          setOffset(10);
        }
        // 检查是否还有更多数据
        setHasMore(results.length >= 10);
        setShowDropdown(true);
      } else {
        if (!isLoadMore) {
          // 无结果时清空状态
          setSearchResults([]);
          setShowDropdown(false);
        }
        setHasMore(false);
      }
    } catch (error) {
      console.error('Search error:', error);
      if (!isLoadMore) {
        // 搜索失败时清空状态
        setSearchResults([]);
        setShowDropdown(false);
      }
    } finally {
      if (isLoadMore) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  };

  // B. JSON 文件上传逻辑
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        setLoading(true);
        const text = event.target?.result as string;
        const parsed = JSON.parse(text);
        
        // 提取收藏数据，兼容多种格式
        let uploadData = [];
        if (parsed.data) {
          // 格式1: { "data": [...] }
          uploadData = parsed.data;
        } else if (parsed.interest) {
          // 格式2: { "interest": [...] } (tofu[208745052].json 格式)
          uploadData = parsed.interest;
        } else if (Array.isArray(parsed)) {
          // 格式3: [...] (直接的列表格式)
          uploadData = parsed;
        }
        
        // 直接调用后端 API 上传数据
        const result = await collectionService.uploadDouban({
          data: uploadData
        });

        // 显示成功通知
        toast.success({
          title: '上传成功',
          description: `成功导入 ${result.sync_count} 条数据`,
          icon: CheckCircle2,
          duration: 3000,
        });

        setJsonError('');
      } catch (err) {
        setJsonError('上传失败，请检查文件格式');
        // 显示错误通知
        toast.error({
          title: '上传失败',
          description: err instanceof Error ? err.message : '上传失败，请重试',
          icon: XCircle,
          duration: 3000,
        });
      } finally {
        setLoading(false);
      }
    };
    reader.readAsText(file);
    // 清空 input 允许重复上传同一文件
    e.target.value = '';
  };

  // C. 最终提交
  const handleOk = async () => {
    try {
      setLoading(true);

      // 构建请求数据
      const requestData = {
        data: [{
          subject: formData.subject,
          collection: {
            type: formData.collectionType || 2, // 默认值为"看过"
            rate: formData.rate,
            comment: formData.comment,
            vol_status: formData.volStatus,
            ep_status: formData.epStatus,
            tags: formData.tags
          }
        }]
      };

      // 调用后端 API
      const result = await collectionService.uploadDouban(requestData);

      // 显示成功通知
      toast.success({
        title: '上传成功',
        description: `成功导入 ${result.sync_count} 条数据`,
        icon: CheckCircle2,
        duration: 3000,
      });

      // 关闭模态框并重置状态
      onClose();
      // 重置状态
      setFormData({
        title: '',
        subject: {
          id: 0,
          date: '',
          images: {
            small: '',
            grid: '',
            large: '',
            medium: '',
            common: ''
          },
          name: '',
          name_cn: '',
          short_summary: '',
          tags: [],
          score: 0,
          type: 0,
          eps: 0,
          volumes: 0,
          source: ''
        },
        cover: '',
        collectionType: 0,
        rate: 0,
        comment: '',
        volStatus: 0,
        epStatus: 0,
        tags: ''
      });
      setKeyword('');
      setSearchResults([]);
      setShowDropdown(false);
      setJsonError('');
    } catch (error) {
      console.error('Upload error:', error);
      // 显示错误通知
      toast.error({
        title: '上传失败',
        description: error instanceof Error ? error.message : '上传失败，请重试',
        icon: XCircle,
        duration: 3000,
      });
    } finally {
      setLoading(false);
    }
  };
  
  // D. 处理搜索结果选择
  const handleResultSelect = (index: number) => {
    const result = searchResults[index];
    if (!result) return;
    
    // 从选中结果中提取数据填入表单
    const subject = result.subject;
    const collection = result.collection;
    
    if (subject) {
      const newFormData: FormData = {
        id: subject.source_id || 0,
        title: subject.name_cn || subject.name || keyword,
        subject: {
          id: subject.source_id || 0,
          date: subject.date || '',
          images: subject.images || {
            small: '',
            grid: '',
            large: '',
            medium: '',
            common: subject.image || ''
          },
          name: subject.name || '',
          name_cn: subject.name_cn || '',
          short_summary: subject.summary || subject.short_summary || `这是关于 "${keyword}" 的自动检索详情。`,
          tags: subject.tags || [],
          score: subject.rating && subject.rating.score ? subject.rating.score : (subject.score || 0),
          type: subject.type || 0,
          eps: subject.eps || 0,
          volumes: subject.volumes || 0,
          source: subject.source || ''
        },
        cover: subject.image || (subject.images && subject.images.common ? subject.images.common : ''),
        collectionType: collection?.type || 0,
        rate: collection?.rate || 0,
        comment: collection?.comment || '',
        volStatus: collection?.vol_status || 0,
        epStatus: collection?.ep_status || 0,
        tags: collection?.tags && Array.isArray(collection.tags) ? collection.tags.join(', ') : ''
      };
      
      setFormData(newFormData);
      setShowDropdown(false);
    }
  };

  // E. 加载更多结果
  const loadMoreResults = () => {
    if (!loadingMore && hasMore && showDropdown) {
      handleSearch(true);
    }
  };

  // F. 处理滚动事件
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    const scrollTop = target.scrollTop;
    const scrollHeight = target.scrollHeight;
    const clientHeight = target.clientHeight;
    
    // 当滚动到距离底部100px时加载更多
    if (scrollHeight - scrollTop - clientHeight < 100) {
      loadMoreResults();
    }
  };

  // --- UI 渲染 ---

  return (
    <>
      <Modal
        open={isOpen}
        title="导入数据"
        onCancel={onClose}
        onOk={handleOk}
        okText={loading ? "处理中..." : "上传/更新"}
        cancelText="取消"
        centered
        width={600}
        okButtonProps={{ loading }}
        destroyOnHidden
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          
          {/* 1. 顶部工具栏 */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {/* 搜索组合框 */}
            <div style={{ position: 'relative', flex: 1 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <Input 
                  placeholder="输入名称 (如: 进击的巨人)" 
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onPressEnter={() => handleSearch(false)}
                  onFocus={() => {
                    // 当Input获得焦点时，如果有搜索结果，显示下拉框
                    if (searchResults.length > 0) {
                      setShowDropdown(true);
                    }
                  }}
                  onBlur={() => {
                    // 当Input失去焦点时，延迟隐藏下拉框，以便点击下拉框项时能够触发
                    setTimeout(() => {
                      setShowDropdown(false);
                    }, 200);
                  }}
                />
                <Button type="primary" onClick={() => handleSearch(false)} loading={loading}>
                    检索
                </Button>
              </div>
              
              {/* 搜索结果悬浮下拉框 */}
              {showDropdown && searchResults.length > 0 && (
                <div 
                  ref={dropdownRef}
                  onScroll={handleScroll}
                  style={{ 
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    zIndex: 50,
                    maxHeight: '300px', 
                    overflowY: 'auto', 
                    marginTop: 4,
                    border: `1px solid ${isDarkMode ? '#374151' : '#e5e7eb'}`, 
                    borderRadius: 8,
                    padding: 8,
                    backgroundColor: isDarkMode ? '#1f2937' : '#ffffff',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)'
                  }}>
                  {searchResults.map((result, index) => {
                    const subject = result.subject;
                    const collection = result.collection;
                    
                    if (!subject) return null;
                    
                    const cover = subject.image || (subject.images && subject.images.common ? subject.images.common : '');
                    const score = subject.rating && subject.rating.score ? subject.rating.score : 0;
                    const hasCollection = !!collection;
                    
                    return (
                      <div
                        key={`${subject.source}-${subject.source_id}`}
                        style={{
                          display: 'flex',
                          gap: 12,
                          padding: 12,
                          borderRadius: 8,
                          marginBottom: 8,
                          backgroundColor: isDarkMode ? '#1f2937' : '#ffffff',
                          border: `1px solid ${isDarkMode ? '#374151' : '#e5e7eb'}`,
                          cursor: 'pointer',
                          transition: 'all 0.2s'
                        }}
                        onClick={() => {
                          handleResultSelect(index);
                        }}
                      >
                        {/* 封面图 */}
                        {cover && (
                          <img
                            src={cover}
                            alt={subject.name}
                            style={{ 
                              width: 60, 
                              height: 80, 
                              objectFit: 'cover', 
                              borderRadius: 4 
                            }}
                          />
                        )}
                        {!cover && (
                          <div style={{ 
                            width: 60, 
                            height: 80, 
                            backgroundColor: '#f3f4f6', 
                            borderRadius: 4, 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center' 
                          }}>
                            <Icon icon={BookOpen} size={24} style={{ color: '#9ca3af' }} />
                          </div>
                        )}
                        
                        {/* 右侧信息 */}
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 'bold', fontSize: 14, color: isDarkMode ? '#f3f4f6' : '#111827' }}>
                              {subject.name_cn || subject.name}
                            </div>
                            
                            {/* 收藏状态标签 */}
                            {hasCollection && (
                              <Tag color="blue" style={{ fontWeight: 600, fontSize: 11 }}>
                                已收藏
                              </Tag>
                            )}
                          </div>
                          
                          {/* 评分信息 */}
                          {score > 0 && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: isDarkMode ? '#9ca3af' : '#6b7280' }}>
                              <Icon icon={Star} size={12} style={{ color: '#f59e0b' }} />
                              <span>{score}</span>
                            </div>
                          )}
                          
                          {/* 标签信息 */}
                          {subject.tags && subject.tags.length > 0 && (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, fontSize: 11, color: isDarkMode ? '#9ca3af' : '#6b7280' }}>
                              {subject.tags.slice(0, 4).map((tag: { name: string }, index: number) => (
                                <Tag key={index} color="gray" style={{ fontSize: 10, fontWeight: 500 }}>
                                  {tag.name}
                                </Tag>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  
                  {/* 加载更多指示器 */}
                  {loadingMore && (
                    <div style={{
                      display: 'flex',
                      justifyContent: 'center',
                      alignItems: 'center',
                      padding: 12,
                      marginTop: 8,
                      borderRadius: 8,
                      backgroundColor: isDarkMode ? '#374151' : '#f9fafb'
                    }}>
                      <div style={{
                        width: 16,
                        height: 16,
                        border: `2px solid ${isDarkMode ? '#4b5563' : '#e5e7eb'}`,
                        borderTop: '2px solid #3b82f6',
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite'
                      }} />
                    </div>
                  )}
                  
                  {/* 没有更多数据提示 */}
                  {!loadingMore && !hasMore && searchResults.length > 0 && (
                    <div style={{
                      textAlign: 'center',
                      padding: 12,
                      marginTop: 8,
                      fontSize: 12,
                      color: isDarkMode ? '#9ca3af' : '#6b7280',
                      backgroundColor: isDarkMode ? '#374151' : '#f9fafb',
                      borderRadius: 8
                    }}>
                      没有更多结果了
                    </div>
                  )}
                </div>
              )}
            </div>
            
            {/* JSON 上传按钮 */}
            <Tooltip title="上传 JSON 文件">
              <Button 
                icon={<Icon icon={FileJson} />}
                onClick={() => fileInputRef.current?.click()}
                loading={loading}
              >
                上传
              </Button>
            </Tooltip>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
          </div>
          
          {/* JSON 上传错误提示 */}
          {jsonError && <div style={{ color: 'red', fontSize: 12 }}>{jsonError}</div>}

          {/* 2. 底部编辑区 */}
          <SubjectForm value={formData} onChange={setFormData} />
        </div>
      </Modal>
    </>
  );
};

export default ImportModal;
