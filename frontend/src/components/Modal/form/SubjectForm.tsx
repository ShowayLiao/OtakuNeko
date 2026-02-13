import React, { useState } from 'react';
import { Input, Select, TextArea, Button, Icon, Tag } from '@lobehub/ui';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { FormData } from '../types';

interface SubjectFormProps {
  value: FormData;
  onChange: (value: FormData) => void;
}

export const SubjectForm: React.FC<SubjectFormProps> = ({ value, onChange }) => {
  const { isDarkMode } = useAppTheme();
  const [showSubjectDetails, setShowSubjectDetails] = useState<boolean>(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Subject 信息栏 */}
      <div style={{ 
        border: `1px solid ${isDarkMode ? '#374151' : '#e5e7eb'}`, 
        borderRadius: 8, 
        padding: 12,
        background: isDarkMode ? '#1f2937' : '#f9fafb'
      }}>
        {/* Subject 栏头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h4 style={{ margin: 0, fontSize: 14, fontWeight: 'bold', color: isDarkMode ? '#f3f4f6' : '#111827' }}>条目信息</h4>
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
          {value.cover && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <img 
                src={value.cover} 
                alt={value.title} 
                style={{ width: 80, height: 120, objectFit: 'cover', borderRadius: 4 }}
              />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>条目名称</span>
                  <Input 
                    value={value.title} 
                    onChange={(e) => onChange({...value, title: e.target.value})}
                    disabled={!showSubjectDetails}
                  />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>条目类型</span>
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
                        value={value.subject.type?.toString() || ''}
                        onChange={(value) => onChange({...value, subject: {...value.subject, type: parseInt(value) || 0}})}
                        disabled={!showSubjectDetails}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>评分</span>
                    <Input 
                      value={value.subject.score || ''} 
                      onChange={(e) => onChange({...value, subject: {...value.subject, score: parseFloat(e.target.value) || 0}})}
                      disabled={!showSubjectDetails}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
          {!value.cover && (
            <div>
              <div>
                <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>条目名称</span>
                <Input 
                  value={value.title} 
                  onChange={(e) => onChange({...value, title: e.target.value})}
                  disabled={!showSubjectDetails}
                />
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>条目类型</span>
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
                      value={value.subject.type?.toString() || ''}
                      onChange={(value) => onChange({...value, subject: {...value.subject, type: parseInt(value) || 0}})}
                      disabled={!showSubjectDetails}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>网站评分</span>
                  <Input 
                    value={value.subject.score || ''} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, score: parseFloat(e.target.value) || 0}})}
                    disabled={!showSubjectDetails}
                  />
                </div>
              </div>
            </div>
          )}
          
          {/* 展开后的详细信息 */}
          {showSubjectDetails && (
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${isDarkMode ? '#374151' : '#e5e7eb'}` }}>
              <div>
                <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>条目简介</span>
                <TextArea 
                  resize={false} 
                  value={value.subject.short_summary} 
                  onChange={(e) => onChange({...value, subject: {...value.subject, short_summary: e.target.value}})}
                />
              </div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>原始名称</span>
                  <Input 
                    value={value.subject.name} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, name: e.target.value}})}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>中文名称</span>
                  <Input 
                    value={value.subject.name_cn} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, name_cn: e.target.value}})}
                  />
                </div>
              </div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>发售/放送日期</span>
                  <Input 
                    value={value.subject.date} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, date: e.target.value}})}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>集数</span>
                  <Input 
                    type="number" 
                    min="0" 
                    value={value.subject.eps} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, eps: parseInt(e.target.value) || 0}})}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>卷数</span>
                  <Input 
                    type="number" 
                    min="0" 
                    value={value.subject.volumes} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, volumes: parseInt(e.target.value) || 0}})}
                  />
                </div>
              </div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>来源</span>
                  <Input 
                    value={value.subject.source} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, source: e.target.value}})}
                  />
                </div>
              </div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>源ID</span>
                  <Input 
                    type="number" 
                    min="0" 
                    value={value.subject.id} 
                    onChange={(e) => onChange({...value, subject: {...value.subject, id: parseInt(e.target.value) || 0}})}
                  />
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>封面图 URL</span>
                <Input 
                  value={value.cover} 
                  onChange={(e) => onChange({...value, cover: e.target.value})}
                />
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Collection 信息栏 */}
      <div style={{ 
        border: `1px solid ${isDarkMode ? '#374151' : '#e5e7eb'}`, 
        borderRadius: 8, 
        padding: 12,
        background: isDarkMode ? '#1f2937' : '#f9fafb'
      }}>
        <h4 style={{ marginBottom: 12, fontSize: 14, fontWeight: 'bold', color: isDarkMode ? '#f3f4f6' : '#111827' }}>收藏信息</h4>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>收藏类型</span>
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
                  value={value.collectionType?.toString() || ''}
                  onChange={(value) => onChange({...value, collectionType: parseInt(value) || 0})}
              />
            </div>
            <div>
              <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>用户评分 (0-10)</span>
              <Input 
                  type="number" 
                  min="0" 
                  max="10" 
                  placeholder="0-10" 
                  value={value.rate || ''}
                  onChange={(e) => onChange({...value, rate: parseInt(e.target.value) || 0})}
              />
            </div>
          </div>
          
          <div>
            <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>评论</span>
            <TextArea 
                resize={false} 
                placeholder="请输入评论"
                value={value.comment || ''}
                onChange={(e) => onChange({...value, comment: e.target.value})}
            />
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>卷数状态</span>
              <Input 
                  type="number" 
                  min="0" 
                  placeholder="0" 
                  value={value.volStatus || ''}
                  onChange={(e) => onChange({...value, volStatus: parseInt(e.target.value) || 0})}
              />
            </div>
            <div>
              <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>集数状态</span>
              <Input 
                  type="number" 
                  min="0" 
                  placeholder="0" 
                  value={value.epStatus || ''}
                  onChange={(e) => onChange({...value, epStatus: parseInt(e.target.value) || 0})}
              />
            </div>
          </div>
          
          <div>
            <span style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#666' }}>标签</span>
            <Input 
                placeholder="请输入标签，用逗号分隔" 
                value={value.tags || ''}
                onChange={(e) => onChange({...value, tags: e.target.value})}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default SubjectForm;
