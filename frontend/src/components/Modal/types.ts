// 1. 定义导入数据的类型结构（根据 bangumi_collection.json）
export interface Subject {
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

export interface FormData {
  // Subject 相关字段
  id?: number;
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

// RSS 相关类型定义
export interface RssFeedItem {
  uid: string;
  url: string;
}

export interface RssItemsResponse {
  items: Record<string, RssFeedItem>;
}

export interface TorrentParams {
  category: string;
  content_layout?: string;
  download_limit: number;
  download_path: string;
  inactive_seeding_time_limit: number;
  operating_mode: string;
  ratio_limit: number;
  save_path: string;
  seeding_time_limit: number;
  share_limit_action: string;
  skip_checking: boolean;
  ssl_certificate: string;
  ssl_dh_params: string;
  ssl_private_key: string;
  tags: string[];
  upload_limit: number;
  use_auto_tmm?: boolean;
  stop_condition?: string;
}

export interface RssRule {
  addPaused?: boolean;
  affectedFeeds: string[];
  assignedCategory: string;
  enabled: boolean;
  episodeFilter: string;
  ignoreDays: number;
  lastMatch?: string;
  mustContain: string;
  mustNotContain: string;
  previouslyMatchedEpisodes: string[];
  priority: number;
  savePath: string;
  smartFilter: boolean;
  torrentContentLayout?: string;
  torrentParams?: TorrentParams;
  useRegex: boolean;
}

export interface RssRulesResponse {
  rules: Record<string, RssRule>;
}

// 后端 API 请求类型
export interface AddRssFeedRequest {
  url: string;
  name?: string;
}

export interface SetRssRuleRequest {
  rule_name: string;
  rule: RssRule;
}

