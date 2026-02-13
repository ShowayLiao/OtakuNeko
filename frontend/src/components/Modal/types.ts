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
