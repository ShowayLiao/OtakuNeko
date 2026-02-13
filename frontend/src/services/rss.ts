import { request } from './client';
import { RssRulesResponse, RssItemsResponse, AddRssFeedRequest, SetRssRuleRequest } from '../components/Modal/types';

// 获取所有 RSS 自动下载规则
export const getRssRules = async (): Promise<RssRulesResponse> => {
  return request<RssRulesResponse>('/rss/rules');
};

// 获取所有 RSS 订阅项
export const getRssItems = async (): Promise<RssItemsResponse> => {
  return request<RssItemsResponse>('/rss/list');
};

// 添加 RSS 订阅源
export const addRssFeed = async (data: AddRssFeedRequest): Promise<void> => {
  return request<void>('/rss/add', {
    method: 'POST',
    body: JSON.stringify(data),
    headers: { 'Content-Type': 'application/json' }
  });
};

// Upsert RSS 订阅源
export const upsertRssFeed = async (data: AddRssFeedRequest): Promise<void> => {
  return request<void>('/rss/upsert', {
    method: 'POST',
    body: JSON.stringify(data),
    headers: { 'Content-Type': 'application/json' }
  });
};

// 设置 RSS 自动下载规则
export const setRssRule = async (data: SetRssRuleRequest): Promise<void> => {
  return request<void>('/rss/set-rule', {
    method: 'POST',
    body: JSON.stringify(data),
    headers: { 'Content-Type': 'application/json' }
  });
};
