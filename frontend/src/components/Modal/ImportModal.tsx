import React, { useState, useRef, useEffect } from 'react';
import { Modal, Button, Input, Icon, TextArea, Select, Tooltip, toast, Tag } from '@lobehub/ui';
import { Search, FileJson, Upload, FileUp, Check, BookOpen, ChevronDown, ChevronUp, XCircle, CheckCircle2, AlertCircle, Star } from 'lucide-react';

// 添加加载动画样式
const style = document.createElement('style');
style.textContent = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;
document.head.appendChild(style);

// 1. 定义导入数据的类型结构（根据 bangumi_collection.json）
interface Subject {
  id: number;
  date: string;
  images?: {
    small?: string;
    grid?: string;
    large?: string;
    medium?: string;
    common?: string;
  };
  name: string;
  name_cn: string;
  short_summary: string;
  tags?: Array<{
    name: string;
    count: number;
    total_cont: number;
  }>;
  score: number;
  type: number;
  eps: number;
  volumes: number;
  source: string;
}

interface FormData {
  // Subject 相关字段
  id?: string;
  title: string; // 显示标题（优先使用name_cn，其次name）
  subject: Subject;
  cover?: string; // 封面图
  // Collection 相关字段
  collectionType?: number;
  rate?: number;
  comment?: string;
  volStatus?: number;
  epStatus?: number;
  tags?: string;
}

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ImportModal = ({ isOpen, onClose }: ImportModalProps) => {
  // --- 状态管理 ---
  
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
  const [searchResults, setSearchResults] = useState<any[]>([]);
  
  // 控制搜索结果下拉框显示
  const [showDropdown, setShowDropdown] = useState<boolean>(false);
  
  // 控制subject详情展开/收起
  const [showSubjectDetails, setShowSubjectDetails] = useState<boolean>(false);
  
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
      // 调用后端 API 进行搜索
      const token = localStorage.getItem('token');
      const currentOffset = isLoadMore ? offset : 0;
      const response = await fetch(`http://localhost:8000/api/v1/subjects/?q=${encodeURIComponent(keyword)}&limit=10&offset=${currentOffset}`, {
        method: 'GET',
        headers: {
          'Authorization': token ? `Bearer ${token}` : '',
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`);
      }

      const data = await response.json();
      
      // 处理后端返回的 UnifiedList 数据
      if (data.items && data.items.length > 0) {
        // 存储完整搜索结果并显示下拉框
        if (isLoadMore) {
          setSearchResults(prev => [...prev, ...data.items]);
          setOffset(prev => prev + 10);
        } else {
          setSearchResults(data.items);
          setOffset(10);
        }
        // 检查是否还有更多数据
        setHasMore(data.items.length >= 10);
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

  // B. JSON 文件解析逻辑
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const text = event.target?.result as string;
        const parsed = JSON.parse(text);
        
        // 处理 bangumi_collection.json 格式
        let subjectData = null;
        let collectionData = null;
        
        // 检查是否为 bangumi_collection.json 格式（包含 data 数组）
        if (parsed.data && Array.isArray(parsed.data) && parsed.data.length > 0) {
          const firstItem = parsed.data[0];
          subjectData = firstItem.subject;
          collectionData = firstItem;
        } else if (parsed.subject) {
          // 检查是否为单个条目格式（包含 subject 对象）
          subjectData = parsed.subject;
          collectionData = parsed;
        } else {
          // 检查是否为直接的表单数据格式
          subjectData = null;
          collectionData = parsed;
        }
        
        // 构建表单数据
        const newFormData: FormData = {
          ...formData,
          title: (subjectData?.name_cn || subjectData?.name || collectionData?.title || ''),
          subject: {
            id: (subjectData?.id || subjectData?.source_id || collectionData?.subjectId || 0),
            date: (subjectData?.date || collectionData?.date || ''),
            images: subjectData?.images || {
              small: '',
              grid: '',
              large: '',
              medium: '',
              common: (subjectData?.image || collectionData?.cover || '')
            },
            name: (subjectData?.name || ''),
            name_cn: (subjectData?.name_cn || ''),
            short_summary: (subjectData?.summary || subjectData?.short_summary || collectionData?.desc || ''),
            tags: subjectData?.tags || [],
            score: (subjectData?.rating && subjectData?.rating.score ? subjectData?.rating.score : (subjectData?.score || collectionData?.rating || 0)),
            type: (subjectData?.type || collectionData?.subjectType || 0),
            eps: (subjectData?.eps || collectionData?.eps || 0),
            volumes: (subjectData?.volumes || collectionData?.volumes || 0),
            source: (subjectData?.source || collectionData?.source || '')
          },
          cover: (subjectData?.image || (subjectData?.images && subjectData?.images.common ? subjectData?.images.common : '') || collectionData?.cover || ''),
          collectionType: (collectionData?.type || collectionData?.collectionType || 0),
          rate: (collectionData?.rate || 0),
          comment: (collectionData?.comment || ''),
          volStatus: (collectionData?.vol_status || collectionData?.volStatus || 0),
          epStatus: (collectionData?.ep_status || collectionData?.epStatus || 0),
          tags: (collectionData?.tags && Array.isArray(collectionData.tags) ? collectionData.tags.join(', ') : (collectionData?.tags || ''))
        };
        
        setFormData(newFormData);
        setJsonError('');
      } catch (err) {
        setJsonError('JSON 格式错误，无法解析');
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
      const now = new Date();
      const updatedAt = now.toISOString();
      
      const requestData = {
        data: [{
          updated_at: updatedAt,
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
      const token = localStorage.getItem('token');
      const response = await fetch('http://localhost:8000/api/v1/collections/sync/manual', {
        method: 'POST',
        headers: {
          'Authorization': token ? `Bearer ${token}` : '',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const result = await response.json();

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
      setShowSubjectDetails(false);
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
                    border: '1px solid #e5e7eb', 
                    borderRadius: 8,
                    padding: 8,
                    backgroundColor: '#ffffff',
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
                          backgroundColor: '#ffffff',
                          border: '1px solid #e5e7eb',
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
                            <div style={{ fontWeight: 'bold', fontSize: 14 }}>
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
                            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#6b7280' }}>
                              <Icon icon={Star} size={12} style={{ color: '#f59e0b' }} />
                              <span>{score}</span>
                            </div>
                          )}
                          
                          {/* 标签信息 */}
                          {subject.tags && subject.tags.length > 0 && (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, fontSize: 11, color: '#6b7280' }}>
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
                      backgroundColor: '#f9fafb'
                    }}>
                      <div style={{
                        width: 16,
                        height: 16,
                        border: '2px solid #e5e7eb',
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
                      color: '#6b7280',
                      backgroundColor: '#f9fafb',
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
              >
                上传
              </Button>
            </Tooltip>
          </div>
          
          {/* JSON 上传错误提示 */}
          {jsonError && <div style={{ color: 'red', fontSize: 12 }}>{jsonError}</div>}

          {/* 2. 底部编辑区 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Subject 信息栏 */}
            <div style={{ 
              border: '1px solid #e5e7eb', 
              borderRadius: 8, 
              padding: 12,
              background: '#f9fafb'
            }}>
              {/* Subject 栏头部 */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h4 style={{ margin: 0, fontSize: 14, fontWeight: 'bold' }}>条目信息</h4>
                <Button 
                  icon={showSubjectDetails ? <Icon icon={ChevronUp} /> : <Icon icon={ChevronDown} />}
                  size="small"
                  onClick={() => setShowSubjectDetails(!showSubjectDetails)}
                >
                  {showSubjectDetails ? '收起' : '展开手动编辑'}
                </Button>
              </div>
              
              {/* Subject 基本信息 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {formData.cover && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <img 
                      src={formData.cover} 
                      alt={formData.title} 
                      style={{ width: 80, height: 120, objectFit: 'cover', borderRadius: 4 }}
                    />
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div>
                        <span style={{ fontSize: 12, color: '#666' }}>条目名称</span>
                        <Input 
                          value={formData.title} 
                          onChange={(e) => setFormData({...formData, title: e.target.value})}
                          disabled={!showSubjectDetails}
                        />
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <div style={{ flex: 1 }}>
                          <span style={{ fontSize: 12, color: '#666' }}>条目类型</span>
                          <Select
                              placeholder="请选择条目类型"
                              options={[
                                  { label: '书籍/小说', value: '1' },
                                  { label: '动画', value: '2' },
                                  { label: '音乐', value: '3' },
                                  { label: '游戏', value: '4' },
                                  { label: '三次元', value: '6' }
                              ]}
                              style={{ width: '100%' }}
                              value={formData.subject.type?.toString() || ''}
                              onChange={(value) => setFormData({...formData, subject: {...formData.subject, type: parseInt(value) || 0}})}
                              disabled={!showSubjectDetails}
                          />
                        </div>
                        <div style={{ flex: 1 }}>
                          <span style={{ fontSize: 12, color: '#666' }}>评分</span>
                          <Input 
                            value={formData.subject.score || ''} 
                            onChange={(e) => setFormData({...formData, subject: {...formData.subject, score: parseFloat(e.target.value) || 0}})}
                            disabled={!showSubjectDetails}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                {!formData.cover && (
                  <div>
                    <div>
                      <span style={{ fontSize: 12, color: '#666' }}>条目名称</span>
                      <Input 
                        value={formData.title} 
                        onChange={(e) => setFormData({...formData, title: e.target.value})}
                        disabled={!showSubjectDetails}
                      />
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>条目类型</span>
                        <Select
                            placeholder="请选择条目类型"
                            options={[
                                { label: '书籍/小说', value: '1' },
                                { label: '动画', value: '2' },
                                { label: '音乐', value: '3' },
                                { label: '游戏', value: '4' },
                                { label: '三次元', value: '6' }
                            ]}
                            style={{ width: '100%' }}
                            value={formData.subject.type?.toString() || ''}
                            onChange={(value) => setFormData({...formData, subject: {...formData.subject, type: parseInt(value) || 0}})}
                            disabled={!showSubjectDetails}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>网站评分</span>
                        <Input 
                          value={formData.subject.score || ''} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, score: parseFloat(e.target.value) || 0}})}
                          disabled={!showSubjectDetails}
                        />
                      </div>
                    </div>
                  </div>
                )}
                
                {/* 展开后的详细信息 */}
                {showSubjectDetails && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                    <div>
                      <span style={{ fontSize: 12, color: '#666' }}>条目简介</span>
                      <TextArea 
                        resize={false} 
                        value={formData.subject.short_summary} 
                        onChange={(e) => setFormData({...formData, subject: {...formData.subject, short_summary: e.target.value}})}
                      />
                    </div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>原始名称</span>
                        <Input 
                          value={formData.subject.name} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, name: e.target.value}})}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>中文名称</span>
                        <Input 
                          value={formData.subject.name_cn} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, name_cn: e.target.value}})}
                        />
                      </div>
                    </div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>发售/放送日期</span>
                        <Input 
                          value={formData.subject.date} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, date: e.target.value}})}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>集数</span>
                        <Input 
                          type="number" 
                          min="0" 
                          value={formData.subject.eps} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, eps: parseInt(e.target.value) || 0}})}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>卷数</span>
                        <Input 
                          type="number" 
                          min="0" 
                          value={formData.subject.volumes} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, volumes: parseInt(e.target.value) || 0}})}
                        />
                      </div>
                    </div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>来源</span>
                        <Input 
                          value={formData.subject.source} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, source: e.target.value}})}
                        />
                      </div>
                    </div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 12, color: '#666' }}>源ID</span>
                        <Input 
                          type="number" 
                          min="0" 
                          value={formData.subject.id} 
                          onChange={(e) => setFormData({...formData, subject: {...formData.subject, id: parseInt(e.target.value) || 0}})}
                        />
                      </div>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <span style={{ fontSize: 12, color: '#666' }}>封面图 URL</span>
                      <Input 
                        value={formData.cover} 
                        onChange={(e) => setFormData({...formData, cover: e.target.value})}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
            
            {/* Collection 信息栏 */}
            <div style={{ 
              border: '1px solid #e5e7eb', 
              borderRadius: 8, 
              padding: 12,
              background: '#f9fafb'
            }}>
              <h4 style={{ marginBottom: 12, fontSize: 14, fontWeight: 'bold' }}>收藏信息</h4>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <span style={{ fontSize: 12, color: '#666' }}>收藏类型</span>
                    <Select
                        placeholder="请选择收藏类型"
                        options={[
                            { label: '想看', value: '1' },
                            { label: '看过', value: '2' },
                            { label: '在看', value: '3' },
                            { label: '搁置', value: '4' },
                            { label: '抛弃', value: '5' }
                        ]}
                        style={{ width: '100%' }}
                        value={formData.collectionType?.toString() || ''}
                        onChange={(value) => setFormData({...formData, collectionType: parseInt(value) || 0})}
                    />
                  </div>
                  <div>
                    <span style={{ fontSize: 12, color: '#666' }}>用户评分 (0-10)</span>
                    <Input 
                        type="number" 
                        min="0" 
                        max="10" 
                        placeholder="0-10" 
                        value={formData.rate || ''}
                        onChange={(e) => setFormData({...formData, rate: parseInt(e.target.value) || 0})}
                    />
                  </div>
                </div>
                
                <div>
                  <span style={{ fontSize: 12, color: '#666' }}>评论</span>
                  <TextArea 
                      resize={false} 
                      placeholder="请输入评论"
                      value={formData.comment || ''}
                      onChange={(e) => setFormData({...formData, comment: e.target.value})}
                  />
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <span style={{ fontSize: 12, color: '#666' }}>卷数状态</span>
                    <Input 
                        type="number" 
                        min="0" 
                        placeholder="0" 
                        value={formData.volStatus || ''}
                        onChange={(e) => setFormData({...formData, volStatus: parseInt(e.target.value) || 0})}
                    />
                  </div>
                  <div>
                    <span style={{ fontSize: 12, color: '#666' }}>集数状态</span>
                    <Input 
                        type="number" 
                        min="0" 
                        placeholder="0" 
                        value={formData.epStatus || ''}
                        onChange={(e) => setFormData({...formData, epStatus: parseInt(e.target.value) || 0})}
                    />
                  </div>
                </div>
                
                <div>
                  <span style={{ fontSize: 12, color: '#666' }}>标签</span>
                  <Input 
                      placeholder="请输入标签，用逗号分隔" 
                      value={formData.tags || ''}
                      onChange={(e) => setFormData({...formData, tags: e.target.value})}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </Modal>
    </>
  );
};

export default ImportModal;