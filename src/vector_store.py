# src/vector_store.py
import json
import os
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer

# 路径定义
DATA_DIR = "data/datasets"
INDEX_DIR = "data/vector_index"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2" # 支持多语言(中英日)的轻量模型

class LocalVectorStore:
    def __init__(self):
        self.index = None
        self.metadata = [] # 存储向量ID对应的动画详细信息
        self.model = None
        
        # 确保目录存在
        if not os.path.exists(INDEX_DIR):
            os.makedirs(INDEX_DIR)
            
    def _load_model(self, log_func=print):
        """懒加载模型 (第一次用到时才加载，节省内存)"""
        if self.model is None:
            log_func("📥 正在加载 Embedding 模型 (首次运行可能需要下载)...")
            self.model = SentenceTransformer(MODEL_NAME)

    def _prepare_text(self, item):
        """
        🚀 优化后的文本构造策略
        结构: [核心标签] + [标题] + [精简简介]
        """
        title = item.get('title', '未知')
        cv = item.get('cv', '未知配音')
        director = item.get('director', '未知导演')
        script = item.get('script', '未知脚本')

        # 1. 标签增强: 放在最前面，权重感最强
        # 将列表转为自然语言描述，模型更好理解
        tags = " ".join(item.get('tags', [])[:8]) # 只要前8个核心Tag
        
        # 2. 简介清洗与截断: 只取前 150 字，去除换行符噪音
        raw_summary = item.get('summary', '') or ""
        summary = raw_summary.replace("\n", " ").strip()[:150]
        
        # 3. 组合
        # 这种格式 "标签: ... 标题: ... 简介: ..." 对模型很友好
        text = f"风格标签: {tags}。 动画标题: {title}。 内容简介: {summary}。 配音演员: {cv}。 导演: {director}。 脚本: {script}。"
        
        return text

    def build_index(self, log_func=print):
        """
        log_func: 前端传进来的更新函数
        """
        self._load_model(log_func)
        
        candidates = []
        # ... (读取数据的逻辑不变) ...
        # 读取已看
        path_watched = os.path.join(DATA_DIR, "dataset_watched.json")
        if os.path.exists(path_watched):
            with open(path_watched, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item['_source'] = 'Watched'
                    candidates.append(item)
                    
        # 读取抛弃
        path_dropped = os.path.join(DATA_DIR, "dataset_dropped.json")
        if os.path.exists(path_dropped):
            with open(path_dropped, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item['_source'] = 'Dropped'
                    candidates.append(item)
        
        if not candidates:
            return "⚠️ 没有找到 dataset 数据。"

        log_func(f"🔄 检测到 {len(candidates)} 条数据，正在进行文本预处理...")

        # 准备 texts
        texts = [self._prepare_text(item) for item in candidates]
        
        log_func(f"🚀 开始向量化运算 (0/{len(texts)})...")
        
        # 🟢 修改点：
        # 1. 关掉 show_progress_bar (因为它只打印在黑窗口，网页看不见，还会造成卡顿假象)
        # 2. 增加完成后的日志
        embeddings = self.model.encode(texts, show_progress_bar=False) 
        
        log_func("✅ 向量化运算完成！正在转换数据格式...")
        embeddings = np.array(embeddings).astype('float32')
        
        log_func("💾 正在构建 FAISS 索引并写入磁盘...")
        
        # 4. 初始化 FAISS 索引
        dimension = embeddings.shape[1] 
        # faiss.normalize_L2(embeddings) # 如果是用余弦相似度需要这行
        self.index = faiss.IndexFlatIP(dimension) # Inner Product
        self.index.add(embeddings)
        
        # 5. 保存
        faiss.write_index(self.index, os.path.join(INDEX_DIR, "anime.index"))
        with open(os.path.join(INDEX_DIR, "anime_meta.pkl"), 'wb') as f:
            pickle.dump(candidates, f)
            
        # 更新内存
        self.metadata = candidates
        
        success_msg = f"🎉 索引构建完成！共索引 {len(candidates)} 部动画。"
        log_func(success_msg)
        
        return success_msg

    def load_index(self):
        """从磁盘加载索引"""
        try:
            self.index = faiss.read_index(os.path.join(INDEX_DIR, "anime.index"))
            with open(os.path.join(INDEX_DIR, "anime_meta.pkl"), 'rb') as f:
                self.metadata = pickle.load(f)
            return True
        except Exception as e:
            print(f"⚠️ 索引加载失败 (可能是首次运行): {e}")
            return False
        
    def search(self, query_text, top_k=20):
        """
        搜索方法保持不变，但传入的 query_text 需要讲究技巧
        """
        if not self.index:
            if not self.load_index(): return []
        
        self._load_model()
        
        # 1. 向量化查询词
        query_vector = self.model.encode([query_text])
        faiss.normalize_L2(query_vector) # 归一化以匹配余弦相似度
        
        # 2. 搜索 Top-K
        distances, indices = self.index.search(query_vector, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue # 无效结果
            
            item = self.metadata[idx]
            similarity = distances[0][i]

            if similarity < 0.3:
                continue # 过滤掉相似度过低的结果
            
            # 数据清洗：只保留 LLM 需要的字段
            results.append({
                "title": item['title'],
                "status": item['_source'], # Watched / Dropped
                "score": item.get('score'),
                "tags": item.get('tags', [])[:5],
                "summary_snippet": (item.get('summary') or "")[:60] + "...",
                "similarity": float(similarity) # 相似度分数
            })
            
        return results

# 全局单例
vector_store = LocalVectorStore()